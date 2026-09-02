from datetime import datetime
from typing import Protocol

from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
    SourceInspection,
    VersionedPayload,
)
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution


class BigQueryPort(Protocol):
    """Read-only metadata/fingerprint operations plus bounded export."""

    query_hash: str
    schema_hash: str

    def inspect(self, source: str) -> SourceInspection:
        """Discover location, provenance and runtime schema."""
        ...

    def dry_run(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        maximum_bytes_billed: int,
    ) -> DryRunEstimate:
        """Estimate bytes without executing the query."""
        ...

    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        """Materialize, export and count one immutable source snapshot."""
        ...


class ManifestStore(Protocol):
    """Persist run checkpoints and resolve completed history."""

    def latest_completed(self, source: str, year: int) -> BatchManifest | None:
        """Return the newest completed run for a partition."""
        ...

    def persist(self, manifest: BatchManifest) -> None:
        """Append an immutable manifest checkpoint."""
        ...


class ObjectStorePort(Protocol):
    """Read landing bytes and create generation-zero Bronze objects."""

    def read(self, uri: str) -> bytes:
        """Read one landing object."""
        ...

    def read_versioned(self, uri: str) -> VersionedPayload:
        """Read bytes pinned to the returned immutable object version."""
        ...

    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        """Copy the selected source generation into a new destination."""
        ...

    def write_immutable(self, uri: str, payload: bytes) -> BronzeObject:
        """Write using the generation-match-zero precondition."""
        ...


class Clock(Protocol):
    """Inject deterministic UTC time into manifests."""

    def now(self) -> datetime:
        """Return the current aware UTC timestamp."""
        ...


class ReleaseStorePort(Protocol):
    """Transactional registry for one six-source release."""

    def begin(self, execution: ReleaseExecution) -> None:
        """Open the release before recording source manifests."""
        ...

    def record(self, execution: ReleaseExecution, manifest: BatchManifest) -> None:
        """Attach one completed source manifest to the open release."""
        ...

    def complete(self, execution: ReleaseExecution) -> None:
        """Mark the release complete after every source is recorded."""
        ...

    def fail(self, execution: ReleaseExecution) -> None:
        """Record terminal failure while preserving the release history."""
        ...
