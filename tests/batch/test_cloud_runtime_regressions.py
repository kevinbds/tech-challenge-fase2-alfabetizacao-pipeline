from datetime import UTC, datetime

import pytest

from alfabetizacao_pipeline.batch.adapters import (
    GcsObjectVersion,
    ImmutableDownload,
    ImmutableUpload,
    QueryExecution,
)
from alfabetizacao_pipeline.batch.errors import ImmutableObjectExistsError, ManifestConflictError
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.google_adapters import RetryEvent, retry_call
from alfabetizacao_pipeline.batch.google_bigquery import build_query_job_config
from alfabetizacao_pipeline.batch.manifest_store import GcsManifestStore
from alfabetizacao_pipeline.batch.models import (
    BatchStatus,
    BigQueryType,
    BronzeObject,
    QueryParameter,
)


class TransientCloudError(Exception):
    pass


class RecordingRetryObserver:
    def __init__(self) -> None:
        self.events: list[RetryEvent] = []

    def retrying(self, event: RetryEvent) -> None:
        self.events.append(event)


class MemoryManifestSdk:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.upload_attempts: int = 0

    def stat(self, uri: str) -> GcsObjectVersion:
        return GcsObjectVersion(uri, 1, 1)

    def download(self, request: ImmutableDownload) -> bytes:
        return self.objects[request.version.uri]

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        self.upload_attempts += 1
        if request.uri in self.objects:
            raise ImmutableObjectExistsError(uri=request.uri)
        self.objects[request.uri] = request.payload
        return BronzeObject(
            uri=request.uri,
            generation=1,
            crc32c="AAAAAA==",
            size_bytes=len(request.payload),
        )

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        return tuple(
            GcsObjectVersion(uri, 1, 1) for uri in sorted(self.objects) if uri.startswith(prefix)
        )


def test_retryable_cloud_operation_has_bounded_observable_attempts() -> None:
    # Given: a retryable operation that fails twice and an observer
    calls = 0
    observer = RecordingRetryObserver()

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientCloudError
        return "ok"

    # When: the bounded retry helper executes it
    result = retry_call(
        "download",
        operation,
        retryable=(TransientCloudError,),
        maximum_attempts=3,
        observer=observer,
    )
    # Then: the final result and both retry decisions are observable
    assert result == "ok"
    assert calls == 3
    assert tuple(event.attempt for event in observer.events) == (1, 2)


def test_retryable_cloud_operation_stops_at_configured_bound() -> None:
    # Given: an operation that never succeeds
    observer = RecordingRetryObserver()

    def operation() -> str:
        raise TransientCloudError

    # When/Then: retry stops after exactly three attempts
    with pytest.raises(TransientCloudError):
        _ = retry_call(
            "upload",
            operation,
            retryable=(TransientCloudError,),
            maximum_attempts=3,
            observer=observer,
        )
    assert tuple(event.attempt for event in observer.events) == (1, 2)


def test_retry_helper_rejects_zero_attempts_and_supports_default_observer() -> None:
    # Given: an invalid bound and a one-time transient failure without an observer
    with pytest.raises(ValueError, match="0"):
        _ = retry_call("invalid", lambda: "unused", retryable=(), maximum_attempts=0)
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TransientCloudError
        return "ok"

    # When: the default observer receives the retry decision
    result = retry_call("default", operation, retryable=(TransientCloudError,))
    # Then: the operation succeeds without requiring a metrics consumer
    assert result == "ok"


def test_gcs_manifest_store_is_persistent_idempotent_and_completion_aware() -> None:
    # Given: a GCS-backed store and two immutable checkpoints for one run
    sdk = MemoryManifestSdk()
    store = GcsManifestStore("gs://control/manifests", sdk)
    incomplete = manifest_fixture(
        ManifestFixtureSpec("run", "uf", 2024, BatchStatus.INCOMPLETE, None)
    )
    completed = incomplete.model_copy(
        update={"status": BatchStatus.COMPLETED, "completed_at": datetime(2025, 1, 1, tzinfo=UTC)}
    )
    # When: checkpoints are persisted and the completed checkpoint is retried
    store.persist(incomplete)
    store.persist(completed)
    store.persist(completed)
    # Then: retry is idempotent and history resolves only the completed checkpoint
    assert sdk.upload_attempts == 3
    assert store.latest_completed("uf", 2024) == completed


def test_gcs_manifest_store_rejects_concurrent_payload_for_same_checkpoint() -> None:
    # Given: one persisted immutable completed checkpoint
    sdk = MemoryManifestSdk()
    store = GcsManifestStore("gs://control/manifests", sdk)
    completed = manifest_fixture(
        ManifestFixtureSpec(
            "run",
            "uf",
            2024,
            BatchStatus.COMPLETED,
            datetime(2025, 1, 1, tzinfo=UTC),
        )
    )
    store.persist(completed)
    conflicting = completed.model_copy(update={"fingerprint": "concurrent-change"})
    # When/Then: generation-zero conflict cannot overwrite the first writer
    with pytest.raises(ManifestConflictError):
        store.persist(conflicting)


def test_bigquery_job_config_carries_bound_year_location_and_byte_cap() -> None:
    # Given: a typed execution with a named annual parameter
    execution = QueryExecution(
        sql="SELECT ano FROM source WHERE ano = @year",
        location="southamerica-east1",
        maximum_bytes_billed=25,
        parameters=(QueryParameter(name="year", data_type=BigQueryType.INT64, value=2024),),
    )
    # When: the concrete SDK configuration is built for dry-run
    config = build_query_job_config(execution, dry_run=True)
    parameter = config.query_parameters[0]
    # Then: the SDK receives a ScalarQueryParameter and the exact billing cap
    assert execution.location == "southamerica-east1"
    assert config.maximum_bytes_billed == 25
    assert config.dry_run is True
    assert (parameter.name, parameter.type_, parameter.value) == ("year", "INT64", 2024)
