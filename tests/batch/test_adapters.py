from hashlib import sha256

import pytest

from alfabetizacao_pipeline.batch.adapters import (
    BigQueryAdapter,
    BigQueryAdapterConfig,
    GcsObjectStore,
    GcsObjectVersion,
    ImmutableCopy,
    ImmutableDownload,
    ImmutableUpload,
    QueryExecution,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    SourceInspectionRequiredError,
)
from alfabetizacao_pipeline.batch.integrity import crc32c_base64
from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
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

    def snapshot(self, execution: QueryExecution) -> SnapshotExport:
        self.executions.append(execution)
        return SnapshotExport(row_count=1, object_uris=("gs://landing/part.parquet",))


class RecordingGcsSdk:
    def __init__(self) -> None:
        self.upload_request: ImmutableUpload | None = None
        self.copy_request: ImmutableCopy | None = None

    def stat(self, uri: str) -> GcsObjectVersion:
        return GcsObjectVersion(uri, 1, 1)

    def download(self, request: ImmutableDownload) -> bytes:
        return request.version.uri.encode()

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        self.upload_request = request
        return BronzeObject(uri=request.uri, generation=1, crc32c="AAAAAA==", size_bytes=1)

    def copy(self, request: ImmutableCopy) -> BronzeObject:
        self.copy_request = request
        return BronzeObject(
            uri=request.destination_uri,
            generation=2,
            crc32c="AAAAAA==",
            size_bytes=1,
        )

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        return (GcsObjectVersion(prefix + "part.parquet", 1, 1),)


class ExistingObjectGcsSdk:
    def __init__(self, payload: bytes) -> None:
        self.payload: bytes = payload
        self.upload_attempts: int = 0

    def stat(self, uri: str) -> GcsObjectVersion:
        return GcsObjectVersion(uri, 7, 2)

    def download(self, request: ImmutableDownload) -> bytes:
        del request
        return self.payload

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        self.upload_attempts += 1
        raise ImmutableObjectExistsError(uri=request.uri)

    def copy(self, request: ImmutableCopy) -> BronzeObject:
        raise ImmutableObjectExistsError(uri=request.destination_uri)

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        del prefix
        return ()


def test_bigquery_adapter_uses_runtime_location_when_querying() -> None:
    sdk = RecordingBigQuerySdk()
    adapter = BigQueryAdapter(
        BigQueryAdapterConfig(
            SourceLocator("basedosdados", "br_inep_avaliacao_alfabetizacao", "uf"),
            "query",
            "schema",
        ),
        sdk,
    )
    _ = adapter.inspect("uf")
    parameters = (QueryParameter(name="year", data_type=BigQueryType.INT64, value=2024),)
    _ = adapter.dry_run("SELECT ano FROM source", parameters, 99)
    _ = adapter.export_snapshot(
        "SELECT ano FROM source",
        parameters,
        "gs://landing/part-*.parquet",
        99,
    )
    assert tuple(execution.location for execution in sdk.executions) == (
        "southamerica-east1",
        "southamerica-east1",
    )
    assert sdk.executions[-1].maximum_bytes_billed == 99


def test_bigquery_adapter_requires_inspection_when_location_is_unknown() -> None:
    adapter = BigQueryAdapter(
        BigQueryAdapterConfig(
            SourceLocator("basedosdados", "br_inep_avaliacao_alfabetizacao", "uf"),
            "query",
            "schema",
        ),
        RecordingBigQuerySdk(),
    )
    with pytest.raises(SourceInspectionRequiredError):
        _ = adapter.dry_run("SELECT ano FROM source", (), 99)


def test_gcs_adapter_forces_generation_zero_when_uploading() -> None:
    sdk = RecordingGcsSdk()
    store = GcsObjectStore(sdk)
    result = store.write_immutable("gs://bronze/part.parquet", b"x")
    assert result.generation == 1
    assert sdk.upload_request is not None
    assert sdk.upload_request.if_generation_match == 0


def test_gcs_adapter_copies_the_exact_generation_that_was_read() -> None:
    sdk = RecordingGcsSdk()
    store = GcsObjectStore(sdk)

    landing = store.read_versioned("gs://landing/part.parquet")
    result = store.copy_immutable(landing.version, "gs://bronze/part.parquet")

    assert result.uri == "gs://bronze/part.parquet"
    assert sdk.copy_request is not None
    assert sdk.copy_request.source.generation == landing.version.generation
    assert sdk.copy_request.if_generation_match == 0


def test_gcs_adapter_reuses_matching_destination_after_copy_conflict() -> None:
    payload = b"same"
    sdk = ExistingObjectGcsSdk(payload)
    store = GcsObjectStore(sdk)
    source = ObjectVersion(
        uri="gs://landing/part.parquet",
        generation=3,
        metageneration=1,
        payload_sha256=sha256(payload).hexdigest(),
    )

    result = store.copy_immutable(source, "gs://bronze/part.parquet")

    assert (result.generation, result.crc32c, result.size_bytes) == (
        7,
        crc32c_base64(payload),
        len(payload),
    )


def test_gcs_adapter_reuses_matching_existing_bronze_bytes() -> None:
    sdk = ExistingObjectGcsSdk(b"same")
    store = GcsObjectStore(sdk)
    result = store.write_immutable("gs://bronze/part.parquet", b"same")
    assert (result.generation, result.crc32c, result.size_bytes) == (7, crc32c_base64(b"same"), 4)
    assert sdk.upload_attempts == 1


def test_gcs_adapter_rejects_different_bytes_after_generation_zero_conflict() -> None:
    sdk = ExistingObjectGcsSdk(b"first")
    store = GcsObjectStore(sdk)
    with pytest.raises(ImmutableObjectExistsError):
        _ = store.write_immutable("gs://bronze/part.parquet", b"second")
    assert sdk.payload == b"first"
