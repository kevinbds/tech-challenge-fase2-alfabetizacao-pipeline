from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, override, runtime_checkable
from uuid import uuid4

from google.api_core.exceptions import (
    Conflict,
    InternalServerError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.cloud import bigquery

if TYPE_CHECKING:
    from collections.abc import Callable, ItemsView, Iterable, Mapping


from alfabetizacao_pipeline.batch.adapters import (
    BigQuerySdkBoundary,
    GcsSdkBoundary,
    QueryExecution,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.bigquery_metadata import (
    BigQueryTableMetadata,
    source_column_from_metadata,
)
from alfabetizacao_pipeline.batch.google_adapters import RetryObserver, retry_call
from alfabetizacao_pipeline.batch.models import (
    DryRunEstimate,
    SnapshotExport,
    SourceIdentity,
    SourceInspection,
)

Scalar = str | int | float | bool | datetime | None
RETRYABLE_GOOGLE_ERRORS = (ServiceUnavailable, TooManyRequests, InternalServerError)
SNAPSHOT_DESTINATION_PATTERN = re.compile(
    r"^gs://[a-z0-9][a-z0-9._-]+/[A-Za-z0-9._~=/+-]*\*\.parquet$"
)
ROW_COUNT_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)")


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """Normalized BigQuery job output used by the domain adapter."""

    rows: tuple[Mapping[str, Scalar], ...]
    bytes_processed: int


class BigQueryClientBoundary(Protocol):
    """Testable boundary around the concrete google-cloud-bigquery client."""

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        """Read table provenance and ordered schema from native metadata."""
        ...

    def execute(self, execution: QueryExecution, *, dry_run: bool, job_id: str) -> QueryOutcome:
        """Submit one location-aware job configured from typed execution data."""
        ...


class _BigQueryRow(Protocol):
    def items(self) -> ItemsView[str, Scalar]: ...


class _BigQueryJobResult(Protocol):
    @property
    def total_bytes_processed(self) -> int | None: ...

    def result(self) -> Iterable[_BigQueryRow]: ...


@runtime_checkable
class _ExistingBigQueryJobReader(Protocol):
    def get_job(self, job_id: str, *, location: str) -> _BigQueryJobResult: ...


def _normalize_query_rows(rows: Iterable[_BigQueryRow]) -> tuple[Mapping[str, Scalar], ...]:
    return tuple(dict(row.items()) for row in rows)


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
        """Discover dataset location and ordered native table metadata."""
        dataset_ref = f"{locator.project}.{locator.dataset}"
        table_ref = f"{dataset_ref}.{locator.table}"
        dataset = self._client.get_dataset(dataset_ref)
        table = self._client.get_table(table_ref)
        location = dataset.location
        if location is None:
            raise ValueError(dataset_ref)
        if not isinstance(table, BigQueryTableMetadata):
            message = "bigquery-table-metadata-contract"
            raise TypeError(message)
        columns = tuple(source_column_from_metadata(field) for field in table.schema)
        return SourceInspection(
            source=locator.table,
            identity=SourceIdentity(
                location=location,
                modified_at=table.modified,
                etag=table.etag,
            ),
            columns=columns,
        )

    def execute(self, execution: QueryExecution, *, dry_run: bool, job_id: str) -> QueryOutcome:
        """Submit one retry-stable job and normalize its result rows."""
        try:
            job = self._client.query(
                execution.sql,
                job_config=build_query_job_config(execution, dry_run=dry_run),
                location=execution.location,
                job_id=job_id,
            )
        except Conflict as error:
            if not isinstance(self._client, _ExistingBigQueryJobReader):
                message = "bigquery-client-missing-get-job"
                raise TypeError(message) from error
            recovered = self._client.get_job(job_id, location=execution.location)
            return self._recovered_outcome(recovered)
        rows: Iterable[bigquery.Row] = job.result()
        return QueryOutcome(
            rows=_normalize_query_rows(rows),
            bytes_processed=int(job.total_bytes_processed or 0),
        )

    def _recovered_outcome(self, job: _BigQueryJobResult) -> QueryOutcome:
        return QueryOutcome(
            rows=_normalize_query_rows(job.result()),
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
        outcome = self._execute("bigquery.dry_run", execution, dry_run=True)
        return DryRunEstimate(bytes_processed=outcome.bytes_processed)

    @override
    def snapshot(self, execution: QueryExecution) -> SnapshotExport:
        """Materialize, export and count one snapshot in a single BigQuery job."""
        destination_uri = execution.destination_uri
        if (
            destination_uri is None
            or SNAPSHOT_DESTINATION_PATTERN.fullmatch(destination_uri) is None
        ):
            message = "invalid-snapshot-destination"
            raise ValueError(message)
        snapshot_sql = (
            "CREATE TEMP TABLE batch_snapshot AS\n"
            f"{execution.sql};\n\n"
            "EXPORT DATA OPTIONS(\n"
            f"  uri='{destination_uri}',\n"
            "  format='PARQUET',\n"
            "  compression='SNAPPY',\n"
            "  overwrite=false\n"
            ") AS\n"
            "SELECT * FROM batch_snapshot;\n\n"
            "SELECT COUNT(*) AS row_count FROM batch_snapshot"
        )
        outcome = self._execute(
            "bigquery.snapshot",
            replace(execution, sql=snapshot_sql),
            dry_run=False,
        )
        if len(outcome.rows) != 1:
            message = "snapshot-row-count"
            raise ValueError(message)
        row = outcome.rows[0]
        raw_row_count = row["row_count"]
        if isinstance(raw_row_count, bool):
            message = "invalid-snapshot-row-count"
            raise TypeError(message)
        if isinstance(raw_row_count, int):
            row_count = raw_row_count
        elif (
            isinstance(raw_row_count, str)
            and ROW_COUNT_PATTERN.fullmatch(raw_row_count) is not None
        ):
            row_count = int(raw_row_count)
        else:
            message = "invalid-snapshot-row-count"
            raise TypeError(message)
        object_uris = tuple(
            version.uri for version in self._landing.list(destination_uri.split("*", maxsplit=1)[0])
        )
        return SnapshotExport(
            row_count=row_count,
            object_uris=object_uris,
        )

    def _call[ResultT](self, operation: str, action: Callable[[], ResultT]) -> ResultT:
        return retry_call(
            operation,
            action,
            retryable=RETRYABLE_GOOGLE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )

    def _execute(
        self,
        operation: str,
        execution: QueryExecution,
        *,
        dry_run: bool,
    ) -> QueryOutcome:
        job_id = f"alfabetizacao_batch_{uuid4().hex}"
        return self._call(
            operation,
            lambda: self._client.execute(execution, dry_run=dry_run, job_id=job_id),
        )
