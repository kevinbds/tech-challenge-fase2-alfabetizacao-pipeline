import pytest
from google.api_core.exceptions import ServiceUnavailable
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch import commands
from alfabetizacao_pipeline.batch.adapters import (
    BigQueryAdapter,
    ImmutableUpload,
    QueryExecution,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.google_adapters import RetryEvent
from alfabetizacao_pipeline.batch.google_bigquery import GoogleBigQuerySdk, QueryOutcome
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk, StoredBlob
from alfabetizacao_pipeline.batch.manifest_store import GcsManifestStore
from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    QueryParameter,
    SourceIdentity,
    SourceInspection,
)
from alfabetizacao_pipeline.batch.production import (
    ProductionComposition,
    ProductionDependencies,
    build_production_composition,
)
from alfabetizacao_pipeline.config import AppSettings


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[RetryEvent] = []

    def retrying(self, event: RetryEvent) -> None:
        self.events.append(event)


class FlakyStorageClient:
    def __init__(self) -> None:
        self.upload_calls: int = 0

    def download(self, bucket: str, name: str) -> bytes:
        return f"{bucket}/{name}".encode()

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        del bucket, name
        self.upload_calls += 1
        if self.upload_calls == 1:
            message = "transient"
            raise ServiceUnavailable(message)
        return StoredBlob(generation=7, crc32c="4waSgw==", size=len(payload))

    def list_names(self, bucket: str, prefix: str) -> tuple[str, ...]:
        del bucket
        return (prefix + "part-00000.parquet",)


class RecordingBigQueryClient:
    def __init__(self) -> None:
        self.executions: list[tuple[QueryExecution, bool]] = []

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(location="EU", etag="etag"),
            columns=SOURCE_CATALOG[locator.table].columns,
        )

    def execute(self, execution: QueryExecution, *, dry_run: bool) -> QueryOutcome:
        self.executions.append((execution, dry_run))
        return QueryOutcome(
            rows=({"row_count": 2, "content_fingerprint": "42"},),
            bytes_processed=11,
        )


def _execution(destination_uri: str | None = None) -> QueryExecution:
    return QueryExecution(
        sql="SELECT @year",
        location="EU",
        maximum_bytes_billed=25,
        parameters=(QueryParameter(name="year", data_type=BigQueryType.INT64, value=2024),),
        destination_uri=destination_uri,
    )


def test_google_storage_adapter_retries_and_returns_sdk_crc32c_metadata() -> None:
    # Given: a concrete storage adapter whose client fails once
    client = FlakyStorageClient()
    observer = RecordingObserver()
    sdk = GoogleGcsSdk("project", client=client, observer=observer)
    # When: an immutable upload succeeds on the bounded retry
    result = sdk.upload(ImmutableUpload(uri="gs://bucket/object", payload=b"123456789"))
    # Then: SDK generation/CRC32C are preserved and retry is observable
    assert (result.generation, result.crc32c, client.upload_calls) == (7, "4waSgw==", 2)
    assert tuple(event.operation for event in observer.events) == ("gcs.upload",)


def test_google_bigquery_adapter_executes_dry_run_fingerprint_and_export() -> None:
    # Given: a concrete BigQuery SDK adapter with injected client and landing lister
    client = RecordingBigQueryClient()
    landing = GoogleGcsSdk("project", client=FlakyStorageClient())
    sdk = GoogleBigQuerySdk("project", landing, client=client)
    # When: all job paths are exercised
    inspection = sdk.inspect(SourceLocator("basedosdados", "dataset", "uf"))
    estimate = sdk.dry_run(_execution())
    fingerprint = sdk.fingerprint(_execution())
    exported = sdk.export(_execution("gs://bucket/run/part-*.parquet"))
    # Then: dry-run is distinct and export resolves exact landing URIs
    assert inspection.identity.location == "EU"
    assert estimate.bytes_processed == 11
    assert (fingerprint.row_count, fingerprint.value) == (2, "42")
    assert exported == ("gs://bucket/run/part-part-00000.parquet",)
    assert tuple(dry_run for _, dry_run in client.executions) == (True, False, False)


def test_google_adapters_fail_closed_on_missing_export_uri_and_invalid_gs_uri() -> None:
    # Given: concrete adapters with injected clients
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())
    query = GoogleBigQuerySdk(
        "project",
        storage,
        client=RecordingBigQueryClient(),
    )
    # When/Then: incomplete typed destinations never reach either SDK
    with pytest.raises(ValueError, match="destination-uri-required"):
        _ = query.export(_execution())
    with pytest.raises(ValueError, match="https://bucket/object"):
        _ = storage.download("https://bucket/object")


def test_production_composition_injects_cloud_ports_without_fixture_fallbacks() -> None:
    # Given: injected SDK boundaries using the same production composition seam
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())
    query_sdk = GoogleBigQuerySdk(
        "project",
        storage,
        client=RecordingBigQueryClient(),
    )
    composition = build_production_composition(
        "uf",
        AppSettings(),
        git_sha="abc",
        image_digest="sha256:abc",
        dependencies=ProductionDependencies(storage=storage, query=query_sdk),
    )
    # When/Then: runtime owns concrete ports and a persistent manifest store
    assert isinstance(composition.runtime.query, BigQueryAdapter)
    assert isinstance(composition.runtime.manifests, GcsManifestStore)


def test_run_dry_run_uses_injected_production_composition_without_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the production CLI path with injected SDK boundaries and deployment provenance
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())
    query_sdk = GoogleBigQuerySdk(
        "project",
        storage,
        client=RecordingBigQueryClient(),
    )
    composition = build_production_composition(
        "uf",
        AppSettings(),
        git_sha="abc",
        image_digest="sha256:abc",
        dependencies=ProductionDependencies(storage=storage, query=query_sdk),
    )

    def factory(
        source: str,
        settings: AppSettings,
        *,
        git_sha: str,
        image_digest: str,
    ) -> ProductionComposition:
        del source, settings, git_sha, image_digest
        return composition

    monkeypatch.setattr(commands, "build_production_composition", factory)
    # When: the root production run is planned locally through the injected seam
    result = CliRunner().invoke(
        commands.app,
        ["run", "--source", "uf", "--year", "2024", "--dry-run"],
        env={
            "ALFABETIZACAO_GIT_SHA": "abc",
            "ALFABETIZACAO_IMAGE_DIGEST": "sha256:abc",
        },
    )
    # Then: the production path succeeds without constructing or calling fixture adapters
    assert result.exit_code == 0
    assert '"query_hash":"fixture-query-hash"' not in result.stdout
