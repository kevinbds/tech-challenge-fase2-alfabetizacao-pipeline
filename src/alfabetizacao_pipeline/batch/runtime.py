from dataclasses import dataclass
from datetime import UTC, datetime

from alfabetizacao_pipeline.batch.ports import BigQueryPort, Clock, ManifestStore, ObjectStorePort


@dataclass(frozen=True, slots=True)
class BatchRuntime:
    """Concrete port bundle used by the batch state machine."""

    query: BigQueryPort
    manifests: ManifestStore
    objects: ObjectStorePort
    clock: Clock


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Production UTC clock implementation."""

    def now(self) -> datetime:
        """Return the current aware UTC timestamp."""
        return datetime.now(tz=UTC)
