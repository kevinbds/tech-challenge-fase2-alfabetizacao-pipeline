import pytest

from alfabetizacao_pipeline.batch.adapters import (
    BigQueryAdapter,
    BigQueryAdapterConfig,
    GcsObjectStore,
    GcsObjectVersion,
    ImmutableDownload,
    ImmutableUpload,
    QueryExecution,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import SourceInspectionRequiredError
from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    BronzeObject,
    ContentFingerprint,
    DryRunEstimate,
    QueryParameter,
    SourceIdentity,
    SourceInspection,
)


class RecordingBigQuerySdk:
    def __init__(self) -> None:
        self.executions: list[QueryExecution] = []

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(location="southamerica-east1", etag="etag"),
            columns=SOURCE_CATALOG[locator.table].columns,
        )

    def dry_run(self, execution: QueryExecution) -> DryRunEstimate:
        self.executions.append(execution)
        return DryRunEstimate(bytes_processed=1)

    def fingerprint(self, execution: QueryExecution) -> ContentFingerprint:
        self.executions.append(execution)
        return ContentFingerprint(row_count=1, value="fp")

    def export(self, execution: QueryExecution) -> tuple[str, ...]:
        self.executions.append(execution)
        return ("gs://landing/part.parquet",)


class RecordingGcsSdk:
    def __init__(self) -> None:
        self.upload_request: ImmutableUpload | None = None

    def stat(self, uri: str) -> GcsObjectVersion:
        return GcsObjectVersion(uri, 1, 1)

    def download(self, request: ImmutableDownload) -> bytes:
        return request.version.uri.encode()

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        self.upload_request = request
        return BronzeObject(uri=request.uri, generation=1, crc32c="AAAAAA==", size_bytes=1)

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        return (GcsObjectVersion(prefix + "part.parquet", 1, 1),)


def test_bigquery_adapter_uses_runtime_location_when_querying() -> None:
    # Given: an adapter whose SDK discovers a non-default location
    sdk = RecordingBigQuerySdk()
    adapter = BigQueryAdapter(
        BigQueryAdapterConfig(
            SourceLocator("basedosdados", "br_inep_avaliacao_alfabetizacao", "uf"),
            "query",
            "schema",
        ),
        sdk,
    )
    # When: inspection precedes a dry-run and export
    _ = adapter.inspect("uf")
    parameters = (QueryParameter(name="year", data_type=BigQueryType.INT64, value=2024),)
    _ = adapter.dry_run("SELECT ano FROM source", parameters, 99)
    _ = adapter.export("EXPORT DATA", parameters, "gs://landing/part-*.parquet", 99)
    # Then: SDK requests carry discovered location and caller cap
    assert tuple(execution.location for execution in sdk.executions) == (
        "southamerica-east1",
        "southamerica-east1",
    )
    assert sdk.executions[-1].maximum_bytes_billed == 99


def test_bigquery_adapter_requires_inspection_when_location_is_unknown() -> None:
    # Given: an adapter that has not inspected its source
    adapter = BigQueryAdapter(
        BigQueryAdapterConfig(
            SourceLocator("basedosdados", "br_inep_avaliacao_alfabetizacao", "uf"),
            "query",
            "schema",
        ),
        RecordingBigQuerySdk(),
    )
    # When/Then: querying is blocked instead of assuming a location
    with pytest.raises(SourceInspectionRequiredError):
        _ = adapter.dry_run("SELECT ano FROM source", (), 99)


def test_gcs_adapter_forces_generation_zero_when_uploading() -> None:
    # Given: a recording typed GCS SDK boundary
    sdk = RecordingGcsSdk()
    store = GcsObjectStore(sdk)
    # When: an immutable Bronze object is written
    result = store.write_immutable("gs://bronze/part.parquet", b"x")
    # Then: the SDK receives the zero-generation precondition
    assert result.generation == 1
    assert sdk.upload_request is not None
    assert sdk.upload_request.if_generation_match == 0
