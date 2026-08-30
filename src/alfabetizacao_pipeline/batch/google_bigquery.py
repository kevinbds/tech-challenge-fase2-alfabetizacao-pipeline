from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, override

from google.api_core.exceptions import InternalServerError, ServiceUnavailable, TooManyRequests
from google.cloud import bigquery

from alfabetizacao_pipeline.batch.adapters import (
    BigQuerySdkBoundary,
    GcsSdkBoundary,
    QueryExecution,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.google_adapters import RetryObserver, retry_call
from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    ContentFingerprint,
    DryRunEstimate,
    SourceColumn,
    SourceIdentity,
    SourceInspection,
)

Scalar = str | int | float | bool | datetime | None
RETRYABLE_GOOGLE_ERRORS = (ServiceUnavailable, TooManyRequests, InternalServerError)


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """Normalized BigQuery job output used by the domain adapter."""

    rows: tuple[Mapping[str, Scalar], ...]
    bytes_processed: int


class BigQueryClientBoundary(Protocol):
    """Testable boundary around the concrete google-cloud-bigquery client."""

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        """Read table provenance and INFORMATION_SCHEMA metadata."""
        ...

    def execute(self, execution: QueryExecution, *, dry_run: bool) -> QueryOutcome:
        """Submit one location-aware job configured from typed execution data."""
        ...


def build_query_job_config(
    execution: QueryExecution,
    *,
    dry_run: bool,
) -> bigquery.QueryJobConfig:
    """Create the real SDK job configuration without interpolating values."""
    return bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        maximum_bytes_billed=execution.maximum_bytes_billed,
        query_parameters=[
            bigquery.ScalarQueryParameter(
                parameter.name,
                parameter.data_type.value,
                parameter.value,
            )
            for parameter in execution.parameters
        ],
    )


class NativeBigQueryClient:
    """Concrete google-cloud-bigquery client facade."""

    def __init__(self, project: str) -> None:
        """Create an authenticated SDK client for the destination project."""
        self._client: bigquery.Client = bigquery.Client(project=project)

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        """Discover dataset location and ordered INFORMATION_SCHEMA columns."""
        dataset_ref = f"{locator.project}.{locator.dataset}"
        table_ref = f"{dataset_ref}.{locator.table}"
        dataset = self._client.get_dataset(dataset_ref)
        table = self._client.get_table(table_ref)
        location = dataset.location
        if location is None:
            raise ValueError(dataset_ref)
        sql_template = (
            "SELECT column_name, data_type, is_nullable "
            "FROM INFORMATION_SCHEMA_TABLE "
            "WHERE table_name = @table_name ORDER BY ordinal_position"
        )
        sql = sql_template.replace(
            "INFORMATION_SCHEMA_TABLE",
            f"`{dataset_ref}.INFORMATION_SCHEMA.COLUMNS`",
        )
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("table_name", "STRING", locator.table)]
        )
        rows = self._client.query(sql, job_config=config, location=location).result()
        columns = tuple(
            SourceColumn(
                name=str(row["column_name"]),
                data_type=BigQueryType(str(row["data_type"])),
                mode="NULLABLE" if str(row["is_nullable"]) == "YES" else "REQUIRED",
            )
            for row in rows
        )
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(
                location=location,
                modified_at=table.modified,
                etag=table.etag,
            ),
            columns=columns,
        )

    def execute(self, execution: QueryExecution, *, dry_run: bool) -> QueryOutcome:
        """Submit one deterministic-id job and normalize its result rows."""
        identity = sha256(
            (execution.sql + execution.location + repr(execution.parameters)).encode("utf-8")
        ).hexdigest()[:24]
        job = self._client.query(
            execution.sql,
            job_config=build_query_job_config(execution, dry_run=dry_run),
            location=execution.location,
            job_id=f"alfabetizacao_batch_{identity}",
        )
        rows: Iterable[bigquery.Row] = job.result()
        normalized = tuple(dict(row.items()) for row in rows)
        return QueryOutcome(
            rows=normalized,
            bytes_processed=int(job.total_bytes_processed or 0),
        )


class GoogleBigQuerySdk(BigQuerySdkBoundary):
    """Production BigQuery SDK adapter with bounded observable retries."""

    def __init__(
        self,
        project: str,
        landing: GcsSdkBoundary,
        *,
        client: BigQueryClientBoundary | None = None,
        observer: RetryObserver | None = None,
        maximum_attempts: int = 3,
    ) -> None:
        """Bind authenticated clients and retry policy."""
        self._client: BigQueryClientBoundary = client or NativeBigQueryClient(project)
        self._landing: GcsSdkBoundary = landing
        self._observer: RetryObserver | None = observer
        self._maximum_attempts: int = maximum_attempts

    @override
    def inspect(self, locator: SourceLocator) -> SourceInspection:
        """Inspect source metadata with bounded retry."""
        return self._call("bigquery.inspect", lambda: self._client.inspect(locator))

    @override
    def dry_run(self, execution: QueryExecution) -> DryRunEstimate:
        """Return SDK-reported bytes from a real dry-run QueryJobConfig."""
        outcome = self._call(
            "bigquery.dry_run",
            lambda: self._client.execute(execution, dry_run=True),
        )
        return DryRunEstimate(bytes_processed=outcome.bytes_processed)

    @override
    def fingerprint(self, execution: QueryExecution) -> ContentFingerprint:
        """Execute and parse the canonical partition fingerprint query."""
        outcome = self._call(
            "bigquery.fingerprint",
            lambda: self._client.execute(execution, dry_run=False),
        )
        if len(outcome.rows) != 1:
            message = "fingerprint-row-count"
            raise ValueError(message)
        row = outcome.rows[0]
        raw_row_count = row["row_count"]
        if not isinstance(raw_row_count, (str, int, float)):
            message = "invalid-fingerprint-row-count"
            raise TypeError(message)
        return ContentFingerprint(
            row_count=int(raw_row_count),
            value=str(row["content_fingerprint"] or 0),
        )

    @override
    def export(self, execution: QueryExecution) -> tuple[str, ...]:
        """Execute export and list its exact immutable landing objects."""
        if execution.destination_uri is None:
            message = "destination-uri-required"
            raise ValueError(message)
        _ = self._call(
            "bigquery.export",
            lambda: self._client.execute(execution, dry_run=False),
        )
        return self._landing.list(execution.destination_uri.split("*", maxsplit=1)[0])

    def _call[ResultT](self, operation: str, action: Callable[[], ResultT]) -> ResultT:
        return retry_call(
            operation,
            action,
            retryable=RETRYABLE_GOOGLE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )
