from collections.abc import ItemsView
from dataclasses import dataclass
from typing import ClassVar, Protocol, TypedDict, override

import pytest
from google.api_core.exceptions import Conflict, ServiceUnavailable
from pydantic import TypeAdapter

from alfabetizacao_pipeline.batch.adapters import QueryExecution, SourceLocator
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.google_bigquery import (
    GoogleBigQuerySdk,
    NativeBigQueryClient,
    QueryOutcome,
)
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk
from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    QueryParameter,
    SourceIdentity,
    SourceInspection,
)
from tests.batch.test_google_production_adapters import FlakyStorageClient

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class QueryJobConfigBoundary(Protocol):
    def to_api_repr(self) -> dict[str, JsonValue]: ...


class QueryParameterTypeDocument(TypedDict):
    type: str


class QueryParameterValueDocument(TypedDict):
    value: str


class QueryParameterDocument(TypedDict):
    name: str
    parameterType: QueryParameterTypeDocument
    parameterValue: QueryParameterValueDocument


class QueryDocument(TypedDict):
    maximumBytesBilled: str
    queryParameters: list[QueryParameterDocument]


class QueryJobConfigDocument(TypedDict):
    dryRun: bool
    query: QueryDocument


class RecordingBigQueryClient:
    def __init__(self) -> None:
        self.executions: list[tuple[QueryExecution, bool, str]] = []

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(location="EU", etag="etag"),
            columns=SOURCE_CATALOG[locator.table].columns,
        )

    def execute(self, execution: QueryExecution, *, dry_run: bool, job_id: str) -> QueryOutcome:
        self.executions.append((execution, dry_run, job_id))
        return QueryOutcome(
            rows=({"row_count": 2, "content_fingerprint": "42"},),
            bytes_processed=11,
        )


class RowCountBigQueryClient(RecordingBigQueryClient):
    def __init__(self, row_count: str | float | bool) -> None:
        super().__init__()
        self.row_count: str | float | bool = row_count

    @override
    def execute(
        self,
        execution: QueryExecution,
        *,
        dry_run: bool,
        job_id: str,
    ) -> QueryOutcome:
        self.executions.append((execution, dry_run, job_id))
        return QueryOutcome(rows=({"row_count": self.row_count},), bytes_processed=11)


class RetryingBigQueryClient:
    def __init__(self) -> None:
        self.execution_ids: list[str] = []
        self.fail_next_execution: bool = False

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(location="EU", etag="etag"),
            columns=SOURCE_CATALOG[locator.table].columns,
        )

    def execute(
        self,
        execution: QueryExecution,
        *,
        dry_run: bool,
        job_id: str,
    ) -> QueryOutcome:
        del execution, dry_run
        self.execution_ids.append(job_id)
        if self.fail_next_execution:
            self.fail_next_execution = False
            message = "transient"
            raise ServiceUnavailable(message)
        return QueryOutcome(
            rows=({"row_count": 2, "content_fingerprint": "42"},),
            bytes_processed=11,
        )


@dataclass(frozen=True, slots=True)
class NativeQueryCall:
    sql: str
    config: QueryJobConfigBoundary
    location: str
    job_id: str


class NativeQueryRow:
    def items(self) -> ItemsView[str, int]:
        return {"row_count": 2}.items()


class NativeQueryJob:
    total_bytes_processed: ClassVar[int] = 11

    def result(self) -> tuple[NativeQueryRow, ...]:
        return (NativeQueryRow(),)


class ConflictRecoveringNativeClient:
    def __init__(self) -> None:
        self.query_calls: list[NativeQueryCall] = []
        self.recovered_job_ids: list[str] = []

    def query(
        self,
        sql: str,
        *,
        job_config: QueryJobConfigBoundary,
        location: str,
        job_id: str,
    ) -> NativeQueryJob:
        self.query_calls.append(NativeQueryCall(sql, job_config, location, job_id))
        message = "duplicate-job"
        raise Conflict(message)

    def get_job(self, job_id: str, *, location: str) -> NativeQueryJob:
        del location
        self.recovered_job_ids.append(job_id)
        return NativeQueryJob()


def query_execution(destination_uri: str | None = None) -> QueryExecution:
    return QueryExecution(
        sql="SELECT @year",
        location="EU",
        maximum_bytes_billed=25,
        parameters=(QueryParameter(name="year", data_type=BigQueryType.INT64, value=2024),),
        destination_uri=destination_uri,
    )


def test_google_bigquery_adapter_executes_dry_run_and_atomic_snapshot() -> None:
    client = RecordingBigQueryClient()
    landing = GoogleGcsSdk("project", client=FlakyStorageClient())
    sdk = GoogleBigQuerySdk("project", landing, client=client)
    inspection = sdk.inspect(SourceLocator("basedosdados", "dataset", "uf"))
    estimate = sdk.dry_run(query_execution())
    snapshot = sdk.snapshot(query_execution("gs://bucket/run/part-*.parquet"))
    assert inspection.identity.location == "EU"
    assert estimate.bytes_processed == 11
    assert snapshot.row_count == 2
    assert snapshot.object_uris == ("gs://bucket/run/part-part-00000.parquet",)
    assert tuple(dry_run for _, dry_run, _ in client.executions) == (True, False)
    snapshot_sql = client.executions[-1][0].sql
    assert "CREATE TEMP TABLE batch_snapshot AS" in snapshot_sql
    assert "EXPORT DATA OPTIONS(" in snapshot_sql
    assert "SELECT COUNT(*) AS row_count FROM batch_snapshot" in snapshot_sql


@pytest.mark.parametrize("row_count", [2.0, True, "02", "+2", " 2"])
def test_google_bigquery_snapshot_rejects_noncanonical_row_count(
    row_count: str | float | bool,
) -> None:
    landing = GoogleGcsSdk("project", client=FlakyStorageClient())
    sdk = GoogleBigQuerySdk("project", landing, client=RowCountBigQueryClient(row_count))

    with pytest.raises(TypeError, match="invalid-snapshot-row-count"):
        _ = sdk.snapshot(query_execution("gs://bucket/run/part-*.parquet"))


def test_google_bigquery_snapshot_accepts_canonical_decimal_row_count() -> None:
    landing = GoogleGcsSdk("project", client=FlakyStorageClient())
    sdk = GoogleBigQuerySdk("project", landing, client=RowCountBigQueryClient("2"))

    assert sdk.snapshot(query_execution("gs://bucket/run/part-*.parquet")).row_count == 2


def test_bigquery_attempt_ids_are_unique_per_call_and_stable_across_retry() -> None:
    client = RetryingBigQueryClient()
    landing = GoogleGcsSdk("project", client=FlakyStorageClient())
    sdk = GoogleBigQuerySdk("project", landing, client=client)
    client.fail_next_execution = True

    execution = query_execution("gs://bucket/run/part-*.parquet")
    _ = sdk.snapshot(execution)
    _ = sdk.snapshot(execution)

    first_attempt, retry_attempt, next_call = client.execution_ids
    assert first_attempt == retry_attempt
    assert next_call != first_attempt


def test_native_bigquery_recovers_the_existing_job_after_duplicate_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ConflictRecoveringNativeClient()

    def factory(*, project: str) -> ConflictRecoveringNativeClient:
        del project
        return client

    monkeypatch.setattr(
        "alfabetizacao_pipeline.batch.google_bigquery.bigquery.Client",
        factory,
    )
    native = NativeBigQueryClient("project")
    execution = query_execution()
    outcome = native.execute(execution, dry_run=False, job_id="batch-attempt")

    call = client.query_calls[0]
    config = TypeAdapter(QueryJobConfigDocument).validate_python(call.config.to_api_repr())
    assert client.recovered_job_ids == ["batch-attempt"]
    assert call.job_id == "batch-attempt"
    assert call.location == execution.location
    assert config["query"]["maximumBytesBilled"] == str(execution.maximum_bytes_billed)
    assert config["dryRun"] is False
    parameter = config["query"]["queryParameters"][0]
    assert (
        parameter["name"],
        parameter["parameterType"]["type"],
        parameter["parameterValue"]["value"],
    ) == ("year", "INT64", "2024")
    assert outcome.bytes_processed == 11
    assert outcome.rows == ({"row_count": 2},)


def test_google_adapters_fail_closed_on_missing_export_uri_and_invalid_gs_uri() -> None:
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())
    query = GoogleBigQuerySdk("project", storage, client=RecordingBigQueryClient())
    with pytest.raises(ValueError, match="invalid-snapshot-destination"):
        _ = query.snapshot(query_execution())
