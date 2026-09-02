from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution, ReleaseStatus
from alfabetizacao_pipeline.batch.release_store import (
    IncompleteReleaseError,
    InMemoryReleaseStore,
    ReleaseConflictError,
)
from tests.batch.release_test_support import completed_manifest, release_execution


def test_release_mapping_separates_ingestion_from_current_verification() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)
    current_verification = datetime(2026, 10, 30, tzinfo=UTC)

    store.record(execution, completed_manifest("uf", verified_at=current_verification))

    mapping = store.snapshot(execution.release_id).files[0]
    assert mapping.ingested_at == datetime(2026, 8, 30, 0, 1, tzinfo=UTC)
    assert mapping.verified_at == current_verification


def test_release_cycle_is_idempotent_and_freezes_six_non_empty_sources() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)
    for source in SOURCE_CATALOG:
        store.record(execution, completed_manifest(source))

    store.complete(execution)
    completed = store.snapshot(execution.release_id)
    for source in SOURCE_CATALOG:
        store.record(execution, completed_manifest(source))
    store.complete(execution)
    replay = store.snapshot(execution.release_id)

    assert completed.status is ReleaseStatus.SUCCEEDED
    assert replay == completed
    assert {mapping.table_name for mapping in replay.files} == set(SOURCE_CATALOG)
    assert len(replay.files) == 6


def test_terminal_release_rejects_mapping_drift() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)

    for source in SOURCE_CATALOG:
        store.record(execution, completed_manifest(source))
    _ = store.complete(execution)
    with pytest.raises(ReleaseConflictError, match="mapping"):
        store.record(execution, completed_manifest("uf", generation=2))


def test_failed_release_reopens_with_an_empty_selection() -> None:
    store = InMemoryReleaseStore()
    first = release_execution()
    store.begin(first)
    store.record(first, completed_manifest("uf"))
    store.fail(first)

    replay = release_execution()
    store.begin(replay)

    snapshot = store.snapshot(replay.release_id)
    assert snapshot.status is ReleaseStatus.RUNNING
    assert snapshot.files == ()


def test_terminal_replays_are_idempotent_for_the_same_release_identity() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)
    for source in SOURCE_CATALOG:
        store.record(execution, completed_manifest(source))
    store.complete(execution)

    completed = store.snapshot(execution.release_id)
    store.begin(execution)
    store.complete(execution)

    failed = InMemoryReleaseStore()
    failed.begin(execution)
    failed.fail(execution)
    failed.fail(execution)

    assert store.snapshot(execution.release_id) == completed
    assert failed.snapshot(execution.release_id).status is ReleaseStatus.FAILED


def test_failed_release_rejects_record_and_complete_until_reopened() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)
    for source in SOURCE_CATALOG:
        store.record(execution, completed_manifest(source))
    store.fail(execution)

    with pytest.raises(ReleaseConflictError, match="failed release"):
        store.record(execution, completed_manifest("uf"))
    with pytest.raises(ReleaseConflictError, match="failed release"):
        store.complete(execution)


def test_release_completion_fails_closed_for_missing_or_empty_sources() -> None:
    store = InMemoryReleaseStore()
    execution = release_execution()
    store.begin(execution)
    for source in tuple(SOURCE_CATALOG)[:-1]:
        store.record(execution, completed_manifest(source))

    with pytest.raises(IncompleteReleaseError, match="alunos"):
        store.complete(execution)

    with pytest.raises(ValidationError):
        _ = completed_manifest("alunos", row_count=0)


@pytest.mark.parametrize(
    "release_id",
    ["batch-202608", "batch-202608-y2024-rbad!", "x' OR 1=1 --"],
)
def test_release_id_rejects_ambiguous_or_sql_shaped_values(release_id: str) -> None:
    with pytest.raises(ValidationError):
        _ = ReleaseExecution(
            release_id=release_id,
            year=2024,
        )
