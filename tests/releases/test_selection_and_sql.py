from datetime import UTC, datetime
from importlib.resources import files

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import (
    IncompleteRunError,
    InvalidReferenceYearError,
    InvalidTableIdentifierError,
)
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
    manifests = tuple(_completed(source) for source in SOURCE_CATALOG)
    release = select_latest_completed(
        manifests,
        "release-1",
        datetime(2025, 4, 1, tzinfo=UTC),
        expected_keys=_expected_keys(),
    )
    assert frozenset((partition.source, partition.year) for partition in release.partitions) == (
        _expected_keys()
    )


def test_release_rejects_catalog_sources_distributed_across_different_years() -> None:
    expected_keys = frozenset(
        (source, 2024 if index % 2 == 0 else 2023) for index, source in enumerate(SOURCE_CATALOG)
    )
    manifests = tuple(_completed(source, year) for source, year in expected_keys)
    with pytest.raises(IncompleteRunError):
        _ = select_latest_completed(
            manifests,
            "release-mixed-years",
            datetime(2025, 4, 1, tzinfo=UTC),
            expected_keys=expected_keys,
        )


def test_promotion_and_rollback_are_transactional_release_updates() -> None:
    promote = promotion_sql("project.ops.active_release")
    rollback = rollback_sql("project.ops.active_release", 2024)
    assert "begin transaction;" in promote.lower()
    assert "assert" in promote.lower()
    assert "commit transaction;" in promote.lower()
    assert "begin transaction;" in rollback.lower()
    assert "assert" in rollback.lower()
    assert "commit transaction;" in rollback.lower()
    assert "prior_release_id" in promote
    assert "release_id" in promote
    assert "create temp table rollback_chain" in rollback.lower()
    assert "prior_release_id" in rollback
    assert "release_id" in rollback
    assert "active_release_id" not in promote + rollback
    assert "previous_release_id" not in promote + rollback


def test_empty_completed_history_fails_closed_when_selecting_release() -> None:
    with pytest.raises(IncompleteRunError):
        _ = select_latest_completed(
            (),
            "release-empty",
            datetime(2025, 4, 1, tzinfo=UTC),
            expected_keys=_expected_keys(),
        )


def test_rollback_renders_the_requested_year_into_the_canonical_script() -> None:
    rollback = rollback_sql("project.ops.active_release", 2023)
    assert "declare target_year int64 default 2023;" in rollback
    assert "rollback target year is absent from active history" in rollback


@pytest.mark.parametrize(
    "reference_year",
    [1999, 2101, "2024", 2024.0, True, None, {"year": 2024}],
)
def test_rollback_rejects_reference_years_that_are_not_strict_ints_in_range(
    reference_year: int,
) -> None:
    with pytest.raises(InvalidReferenceYearError):
        _ = rollback_sql("project.ops.active_release", reference_year)


@pytest.mark.parametrize("reference_year", [2000, 2100])
def test_rollback_accepts_the_reference_year_range_boundaries(reference_year: int) -> None:
    rollback = rollback_sql("project.ops.active_release", reference_year)
    assert f"declare target_year int64 default {reference_year};" in rollback


@pytest.mark.parametrize(
    "table",
    [
        "project.other.active_release",
        "project.ops.other_pointer",
    ],
)
def test_release_sql_rejects_noncanonical_pointer_tables(table: str) -> None:
    with pytest.raises(InvalidTableIdentifierError):
        _ = rollback_sql(table, 2024)


def test_release_pointer_model_rejects_blank_identifiers() -> None:
    with pytest.raises(ValidationError):
        _ = ActiveRelease(release_id="", prior_release_id="")


def test_release_sql_templates_are_available_as_package_resources() -> None:
    templates = files("alfabetizacao_pipeline.releases").joinpath("templates")

    assert templates.joinpath("promote_release.sql").is_file()
    assert templates.joinpath("rollback_release.sql").is_file()
