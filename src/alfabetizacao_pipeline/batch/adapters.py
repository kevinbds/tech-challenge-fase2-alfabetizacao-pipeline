from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol

from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    SourceInspectionRequiredError,
)
from alfabetizacao_pipeline.batch.integrity import crc32c_base64
from alfabetizacao_pipeline.batch.models import (
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
    SourceInspection,
    VersionedPayload,
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
    parameters: tuple[QueryParameter, ...]
    destination_uri: str | None = None


@dataclass(frozen=True, slots=True)
class ImmutableUpload:
    """GCS upload request whose only legal generation precondition is zero."""

    uri: str
    payload: bytes
    if_generation_match: Literal[0] = 0


@dataclass(frozen=True, slots=True)
class GcsObjectVersion:
    """Exact immutable GCS object version selected from metadata."""

    uri: str
    generation: int
    metageneration: int


@dataclass(frozen=True, slots=True)
class ImmutableDownload:
    """Read request pinned to one generation and metageneration."""

    version: GcsObjectVersion


@dataclass(frozen=True, slots=True)
class ImmutableCopy:
    """Server-side copy pinned to the selected source generation."""

    source: GcsObjectVersion
    destination_uri: str
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
        """Read dataset location, table provenance and native schema metadata."""
        ...

    def dry_run(self, execution: QueryExecution) -> DryRunEstimate:
        """Return bytes without executing query work."""
        ...

    def snapshot(self, execution: QueryExecution) -> SnapshotExport:
        """Materialize, export and count a snapshot in one query job."""
        ...


class GcsSdkBoundary(Protocol):
    """Narrow typed boundary for google-cloud-storage implementations."""

    def stat(self, uri: str) -> GcsObjectVersion:
        """Resolve the generation and metageneration for one object URI."""
        ...

    def download(self, request: ImmutableDownload) -> bytes:
        """Download one exact object generation."""
        ...

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        """Upload and return generation, CRC32C and size metadata."""
        ...

    def copy(self, request: ImmutableCopy) -> BronzeObject:
        """Copy one source generation into a new destination object."""
        ...

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        """List exact object URIs below a stable control prefix."""
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

    def dry_run(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        maximum_bytes_billed: int,
    ) -> DryRunEstimate:
        """Perform mandatory location-aware dry-run with no billing allowance."""
        return self.sdk.dry_run(
            QueryExecution(sql, self._required_location(), maximum_bytes_billed, parameters)
        )

    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        """Execute one atomic snapshot job at the discovered location and cap."""
        return self.sdk.snapshot(
            QueryExecution(
                sql,
                self._required_location(),
                maximum_bytes_billed,
                parameters,
                destination_uri,
            )
        )

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
        return self.read_versioned(uri).payload

    def read_versioned(self, uri: str) -> VersionedPayload:
        """Download bytes pinned to their resolved GCS generation."""
        version = self.sdk.stat(uri)
        payload = self.sdk.download(ImmutableDownload(version))
        return VersionedPayload(
            version=ObjectVersion(
                uri=version.uri,
                generation=version.generation,
                metageneration=version.metageneration,
                payload_sha256=sha256(payload).hexdigest(),
            ),
            payload=payload,
        )

    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        """Copy the fingerprinted source generation into new Bronze storage."""
        request = ImmutableCopy(
            source=GcsObjectVersion(
                uri=source.uri,
                generation=source.generation,
                metageneration=source.metageneration,
            ),
            destination_uri=destination_uri,
        )
        try:
            return self.sdk.copy(request)
        except ImmutableObjectExistsError:
            version = self.sdk.stat(destination_uri)
            existing = self.sdk.download(ImmutableDownload(version))
            if sha256(existing).hexdigest() != source.payload_sha256:
                raise
            return BronzeObject(
                uri=destination_uri,
                generation=version.generation,
                crc32c=crc32c_base64(existing),
                size_bytes=len(existing),
            )

    def write_immutable(self, uri: str, payload: bytes) -> BronzeObject:
        """Upload a Bronze object or reuse an identical immutable generation."""
        try:
            return self.sdk.upload(ImmutableUpload(uri=uri, payload=payload))
        except ImmutableObjectExistsError:
            version = self.sdk.stat(uri)
            existing = self.sdk.download(ImmutableDownload(version))
            if existing != payload:
                raise
            return BronzeObject(
                uri=uri,
                generation=version.generation,
                crc32c=crc32c_base64(existing),
                size_bytes=len(existing),
            )
