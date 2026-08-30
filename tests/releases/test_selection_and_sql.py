from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.releases.models import ActiveRelease
from alfabetizacao_pipeline.releases.selector import select_latest_completed
from alfabetizacao_pipeline.releases.sql import promotion_sql, rollback_sql


def _expected_keys(year: int = 2024) -> frozenset[tuple[str, int]]:
    return frozenset((source, year) for source in SOURCE_CATALOG)


def _completed(source: str, year: int = 2024) -> BatchManifest:
    return manifest_fixture(
        ManifestFixtureSpec(
            f"{source}-{year}",
            source,
            year,
            BatchStatus.COMPLETED,
            datetime(2025, 1, 1, tzinfo=UTC),
        )
    )


def test_release_requires_exactly_one_completed_manifest_per_expected_partition() -> None:
    # Given: one completed manifest for each challenge source in the release year
    manifests = tuple(_completed(source) for source in SOURCE_CATALOG)
    # When: the explicit partition set is selected
    release = select_latest_completed(
        manifests,
        "release-1",
        datetime(2025, 4, 1, tzinfo=UTC),
        expected_keys=_expected_keys(),
    )
    # Then: all and only the expected partitions are mapped
    assert frozenset((partition.source, partition.year) for partition in release.partitions) == (
        _expected_keys()
    )


def test_release_rejects_catalog_sources_distributed_across_different_years() -> None:
    # Given: the six catalog sources are expected, but split across two years
    expected_keys = frozenset(
        (source, 2024 if index % 2 == 0 else 2023) for index, source in enumerate(SOURCE_CATALOG)
    )
    manifests = tuple(_completed(source, year) for source, year in expected_keys)
    # When/Then: each represented year must independently contain every catalog source
    with pytest.raises(IncompleteRunError):
        _ = select_latest_completed(
            manifests,
            "release-mixed-years",
            datetime(2025, 4, 1, tzinfo=UTC),
            expected_keys=expected_keys,
        )


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
        _ = select_latest_completed(
            (),
            "release-empty",
            datetime(2025, 4, 1, tzinfo=UTC),
            expected_keys=_expected_keys(),
        )


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
