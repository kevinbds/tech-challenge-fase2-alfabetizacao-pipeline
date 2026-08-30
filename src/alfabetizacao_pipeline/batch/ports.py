from datetime import datetime
from typing import Protocol

from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BronzeObject,
    ContentFingerprint,
    DryRunEstimate,
    SourceInspection,
)


class BigQueryPort(Protocol):
    """Read-only metadata/fingerprint operations plus bounded export."""

    query_hash: str
    schema_hash: str

    def inspect(self, source: str) -> SourceInspection:
        """Discover location, provenance and runtime schema."""
        ...

    def dry_run(self, sql: str) -> DryRunEstimate:
        """Estimate bytes without executing the query."""
        ...

    def compute_fingerprint(self, sql: str, maximum_bytes_billed: int) -> ContentFingerprint:
        """Execute the bounded content identity query."""
        ...

    def export(self, sql: str, maximum_bytes_billed: int) -> tuple[str, ...]:
        """Export a partition to immutable landing objects."""
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

    def write_immutable(self, uri: str, payload: bytes) -> BronzeObject:
        """Write using the generation-match-zero precondition."""
        ...


class Clock(Protocol):
    """Inject deterministic UTC time into manifests."""

    def now(self) -> datetime:
        """Return the current aware UTC timestamp."""
        ...
