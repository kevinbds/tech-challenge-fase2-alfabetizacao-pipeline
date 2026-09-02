from dataclasses import dataclass
from typing import Final, override

from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.batch.release_models import (
    ReleaseExecution,
    ReleaseFileMapping,
    ReleaseSnapshot,
    ReleaseStatus,
)

RELEASE_SOURCES: Final = (
    "uf",
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "municipio",
    "alunos",
)


@dataclass(frozen=True, slots=True)
class ReleaseConflictError(Exception):
    """Reject a release mutation that violates identity or state invariants."""

    reason: str

    @override
    def __str__(self) -> str:
        return f"release conflict: {self.reason}"


@dataclass(frozen=True, slots=True)
class IncompleteReleaseError(Exception):
    """Report the required source tables absent from a candidate release."""

    missing_sources: tuple[str, ...]

    @override
    def __str__(self) -> str:
        return f"release missing non-empty sources: {','.join(self.missing_sources)}"


class InMemoryReleaseStore:
    """Deterministic transactional fake used by local release QA."""

    def __init__(self) -> None:
        """Initialize an empty deterministic release registry."""
        self._releases: dict[str, ReleaseSnapshot] = {}

    def begin(self, execution: ReleaseExecution) -> None:
        """Open a new candidate or replay the same release identity."""
        current = self._releases.get(execution.release_id)
        if current is None:
            self._releases[execution.release_id] = ReleaseSnapshot(
                release_id=execution.release_id,
                year=execution.year,
                status=ReleaseStatus.RUNNING,
                baseline_release_id="__bootstrap__",
                files=(),
            )
            return
        if current.year != execution.year:
            raise ReleaseConflictError(reason="reference year differs")
        if current.status is ReleaseStatus.FAILED:
            self._releases[execution.release_id] = current.model_copy(
                update={
                    "status": ReleaseStatus.RUNNING,
                    "baseline_release_id": "__bootstrap__",
                    "files": (),
                }
            )
            return

    def record(self, execution: ReleaseExecution, manifest: BatchManifest) -> None:
        """Record immutable mappings from a completed source manifest."""
        current = self._required(execution.release_id)
        self._require_matching_year(current, execution)
        if current.status is ReleaseStatus.FAILED:
            raise ReleaseConflictError(reason="failed release cannot record mappings")
        if (
            manifest.status is not BatchStatus.COMPLETED
            or manifest.completed_at is None
            or manifest.verified_at is None
        ):
            raise ReleaseConflictError(reason="mapping requires a completed manifest")
        if manifest.source not in RELEASE_SOURCES or manifest.year != execution.year:
            raise ReleaseConflictError(reason="mapping source or year differs from release")
        if not manifest.bronze_objects:
            raise IncompleteReleaseError(missing_sources=(manifest.source,))
        mappings = tuple(
            ReleaseFileMapping(
                release_id=execution.release_id,
                table_name=manifest.source,
                year=manifest.year,
                file_uri=bronze.uri,
                source_run_id=manifest.run_id,
                row_count=manifest.row_count,
                generation=bronze.generation,
                crc32c=bronze.crc32c,
                ingested_at=manifest.completed_at,
                verified_at=manifest.verified_at,
            )
            for bronze in manifest.bronze_objects
        )
        indexed = {(item.table_name, item.file_uri): item for item in current.files}
        for mapping in mappings:
            observed = indexed.get((mapping.table_name, mapping.file_uri))
            if observed is not None and observed != mapping:
                raise ReleaseConflictError(reason="mapping differs from immutable selection")
            indexed[(mapping.table_name, mapping.file_uri)] = mapping
        if current.status is not ReleaseStatus.RUNNING and set(indexed.values()) != set(
            current.files
        ):
            raise ReleaseConflictError(reason="mapping cannot change after succeeded")
        self._releases[execution.release_id] = current.model_copy(
            update={"files": tuple(sorted(indexed.values(), key=lambda item: item.file_uri))}
        )

    def complete(self, execution: ReleaseExecution) -> None:
        """Complete a candidate only when all six sources are non-empty."""
        current = self._required(execution.release_id)
        self._require_matching_year(current, execution)
        if current.status is ReleaseStatus.FAILED:
            raise ReleaseConflictError(reason="failed release cannot be completed")
        present = {mapping.table_name for mapping in current.files if mapping.row_count > 0}
        missing = tuple(source for source in RELEASE_SOURCES if source not in present)
        if missing:
            raise IncompleteReleaseError(missing_sources=missing)
        run_counts = {
            source: len({item.source_run_id for item in current.files if item.table_name == source})
            for source in RELEASE_SOURCES
        }
        if any(count != 1 for count in run_counts.values()):
            raise ReleaseConflictError(reason="each source requires exactly one source run")
        if current.status is ReleaseStatus.RUNNING:
            self._releases[execution.release_id] = current.model_copy(
                update={"status": ReleaseStatus.SUCCEEDED}
            )

    def fail(self, execution: ReleaseExecution) -> None:
        """Fail an unpublished candidate while preserving terminal-state checks."""
        current = self._required(execution.release_id)
        self._require_matching_year(current, execution)
        if current.status is ReleaseStatus.FAILED:
            return
        if current.status in (ReleaseStatus.ACTIVE, ReleaseStatus.INACTIVE):
            raise ReleaseConflictError(reason="published release cannot fail")
        self._releases[execution.release_id] = current.model_copy(
            update={"status": ReleaseStatus.FAILED}
        )

    def snapshot(self, release_id: str) -> ReleaseSnapshot:
        """Return the immutable observable snapshot for a release."""
        return self._required(release_id)

    def _required(self, release_id: str) -> ReleaseSnapshot:
        current = self._releases.get(release_id)
        if current is None:
            raise ReleaseConflictError(reason="release was not begun")
        return current

    @staticmethod
    def _require_matching_year(current: ReleaseSnapshot, execution: ReleaseExecution) -> None:
        if current.year != execution.year:
            raise ReleaseConflictError(reason="reference year differs")
