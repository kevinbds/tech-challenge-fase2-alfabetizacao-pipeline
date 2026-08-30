from dataclasses import dataclass
from typing import Literal, Protocol

from alfabetizacao_pipeline.batch.errors import SourceInspectionRequiredError
from alfabetizacao_pipeline.batch.models import (
    BronzeObject,
    ContentFingerprint,
    DryRunEstimate,
    SourceInspection,
)


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """Qualified source identity supplied to the BigQuery SDK boundary."""

    project: str
    dataset: str
    table: str


@dataclass(frozen=True, slots=True)
class QueryExecution:
    """Location-aware, byte-capped query request for the SDK boundary."""

    sql: str
    location: str
    maximum_bytes_billed: int


@dataclass(frozen=True, slots=True)
class ImmutableUpload:
    """GCS upload request whose only legal generation precondition is zero."""

    uri: str
    payload: bytes
    if_generation_match: Literal[0] = 0


@dataclass(frozen=True, slots=True)
class BigQueryAdapterConfig:
    """Pinned hashes and locator bound to one adapter instance."""

    locator: SourceLocator
    query_hash: str
    schema_hash: str


class BigQuerySdkBoundary(Protocol):
    """Narrow typed boundary for google-cloud-bigquery implementations."""

    def inspect(self, locator: SourceLocator) -> SourceInspection:
        """Read dataset location, table provenance and INFORMATION_SCHEMA columns."""
        ...

    def dry_run(self, execution: QueryExecution) -> DryRunEstimate:
        """Return bytes without executing query work."""
        ...

    def fingerprint(self, execution: QueryExecution) -> ContentFingerprint:
        """Run the explicit content fingerprint query under the same cap."""
        ...

    def export(self, execution: QueryExecution) -> tuple[str, ...]:
        """Run EXPORT DATA and return exact landing object URIs."""
        ...


class GcsSdkBoundary(Protocol):
    """Narrow typed boundary for google-cloud-storage implementations."""

    def download(self, uri: str) -> bytes:
        """Download one exact object generation."""
        ...

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        """Upload and return generation, CRC32C and size metadata."""
        ...


class BigQueryAdapter:
    """BigQuery port that propagates discovered location and billing ceiling."""

    def __init__(
        self,
        config: BigQueryAdapterConfig,
        sdk: BigQuerySdkBoundary,
    ) -> None:
        """Bind one official table contract to its SDK boundary."""
        self.locator: SourceLocator = config.locator
        self.sdk: BigQuerySdkBoundary = sdk
        self.query_hash: str = config.query_hash
        self.schema_hash: str = config.schema_hash
        self._location: str | None = None

    def inspect(self, source: str) -> SourceInspection:
        """Discover and retain the source location for subsequent queries."""
        del source
        inspection = self.sdk.inspect(self.locator)
        self._location = inspection.identity.location
        return inspection

    def dry_run(self, sql: str) -> DryRunEstimate:
        """Perform mandatory location-aware dry-run with no billing allowance."""
        return self.sdk.dry_run(QueryExecution(sql, self._required_location(), 1))

    def compute_fingerprint(self, sql: str, maximum_bytes_billed: int) -> ContentFingerprint:
        """Compute content identity under the configured planner ceiling."""
        return self.sdk.fingerprint(
            QueryExecution(sql, self._required_location(), maximum_bytes_billed)
        )

    def export(self, sql: str, maximum_bytes_billed: int) -> tuple[str, ...]:
        """Execute export at the discovered location and authorized ceiling."""
        return self.sdk.export(QueryExecution(sql, self._required_location(), maximum_bytes_billed))

    def _required_location(self) -> str:
        if self._location is None:
            raise SourceInspectionRequiredError(source=self.locator.table)
        return self._location


class GcsObjectStore:
    """Object store port that always submits generation-match zero."""

    def __init__(self, sdk: GcsSdkBoundary) -> None:
        """Bind the typed storage SDK boundary."""
        self.sdk: GcsSdkBoundary = sdk

    def read(self, uri: str) -> bytes:
        """Download one landing object."""
        return self.sdk.download(uri)

    def write_immutable(self, uri: str, payload: bytes) -> BronzeObject:
        """Upload a Bronze object with an unchangeable zero precondition."""
        return self.sdk.upload(ImmutableUpload(uri=uri, payload=payload))
