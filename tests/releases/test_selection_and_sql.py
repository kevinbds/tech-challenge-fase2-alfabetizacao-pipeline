from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchStatus
from alfabetizacao_pipeline.releases.models import ActiveRelease
from alfabetizacao_pipeline.releases.selector import select_latest_completed
from alfabetizacao_pipeline.releases.sql import promotion_sql, rollback_sql


def test_latest_completed_excludes_failed_and_incomplete_runs_when_selected() -> None:
    # Given: completed, failed and incomplete runs for one annual partition
    manifests = (
        manifest_fixture(
            ManifestFixtureSpec(
                "old", "uf", 2024, BatchStatus.COMPLETED, datetime(2025, 1, 1, tzinfo=UTC)
            )
        ),
        manifest_fixture(
            ManifestFixtureSpec(
                "failed", "uf", 2024, BatchStatus.FAILED, datetime(2025, 2, 1, tzinfo=UTC)
            )
        ),
        manifest_fixture(
            ManifestFixtureSpec(
                "new", "uf", 2024, BatchStatus.COMPLETED, datetime(2025, 3, 1, tzinfo=UTC)
            )
        ),
        manifest_fixture(ManifestFixtureSpec("partial", "uf", 2024, BatchStatus.INCOMPLETE, None)),
    )
    # When: a release mapping is selected
    release = select_latest_completed(manifests, "release-1", datetime(2025, 4, 1, tzinfo=UTC))
    # Then: only the newest completed run is used
    assert release.partitions[0].run_id == "new"


def test_promotion_and_rollback_are_transactional_pointer_updates() -> None:
    # Given: candidate and active release identifiers
    # When: promotion and rollback SQL are built
    promote = promotion_sql("project.ops.active_release")
    rollback = rollback_sql("project.ops.active_release")
    # Then: both assert singleton cardinality and contain no DDL
    assert "BEGIN TRANSACTION" in promote
    assert "ASSERT" in promote
    assert "COMMIT TRANSACTION" in promote
    assert "BEGIN TRANSACTION" in rollback
    assert "ASSERT" in rollback
    assert "COMMIT TRANSACTION" in rollback
    assert "CREATE TABLE" not in promote.upper()
    assert "DROP TABLE" not in rollback.upper()


def test_empty_completed_history_fails_closed_when_selecting_release() -> None:
    # Given: no completed manifests
    # When/Then: a candidate release cannot be constructed without partitions
    with pytest.raises(IncompleteRunError):
        _ = select_latest_completed((), "release-empty", datetime(2025, 4, 1, tzinfo=UTC))


def test_rollback_asserts_previous_release_is_present_before_pointer_swap() -> None:
    # Given: the singleton release table
    # When: rollback SQL is generated
    rollback = rollback_sql("project.ops.active_release")
    # Then: NULL previous pointers are rejected before the UPDATE
    assert "previous_release_id IS NOT NULL" in rollback


def test_release_pointer_model_rejects_blank_identifiers() -> None:
    # Given: blank active and previous release identifiers
    # When/Then: typed state cannot represent nullable promotion targets
    with pytest.raises(ValidationError):
        _ = ActiveRelease(active_release_id="", previous_release_id="")
