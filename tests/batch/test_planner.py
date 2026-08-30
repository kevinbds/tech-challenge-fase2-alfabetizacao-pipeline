from datetime import UTC, datetime

import pytest

from alfabetizacao_pipeline.batch.errors import CostLimitExceededError
from alfabetizacao_pipeline.batch.fakes import (
    ContentIdentityFixture,
    FakeBigQuery,
    InMemoryManifestStore,
    ManifestFixtureSpec,
    manifest_fixture,
)
from alfabetizacao_pipeline.batch.models import BatchRequest, BatchStatus, DryRunEstimate
from alfabetizacao_pipeline.batch.planner import plan_batch


@pytest.mark.parametrize(("estimated", "blocked"), [(24, False), (25, False), (26, True)])
def test_cost_cap_blocks_only_above_limit_when_planning(estimated: int, blocked: bool) -> None:
    # Given: a 25-byte cap and a dry-run estimate around its boundary
    query = FakeBigQuery(estimate=DryRunEstimate(bytes_processed=estimated))
    request = BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=True)
    # When: the batch is planned
    if blocked:
        # Then: above-cap work is rejected before execution
        with pytest.raises(CostLimitExceededError):
            _ = plan_batch(request, query, InMemoryManifestStore())
        assert query.executed_queries == 0
    else:
        # Then: below/equal work remains a dry-run with no writes
        result = plan_batch(request, query, InMemoryManifestStore())
        assert result.status is BatchStatus.PLANNED
        assert query.executed_queries == 0


def test_skip_requires_query_schema_and_fingerprint_match_when_planning() -> None:
    # Given: a completed manifest matching all three content identities
    query = FakeBigQuery(estimate=DryRunEstimate(bytes_processed=1))
    previous = manifest_fixture(
        ManifestFixtureSpec(
            run_id="previous-run",
            source="uf",
            year=2024,
            status=BatchStatus.COMPLETED,
            completed_at=datetime(2025, 1, 1, tzinfo=UTC),
            identity=ContentIdentityFixture(
                query_hash=query.query_hash,
                schema_hash=query.schema_hash,
                fingerprint=query.fingerprint,
            ),
        )
    )
    store = InMemoryManifestStore((previous,))
    # When: the same partition is planned again
    result = plan_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        query,
        store,
    )
    # Then: execution is skipped safely
    assert result.status is BatchStatus.SKIPPED


def test_changed_fingerprint_creates_new_run_when_replanned() -> None:
    # Given: an old completed run and a corrected upstream partition
    query = FakeBigQuery(estimate=DryRunEstimate(bytes_processed=1), fingerprint="new-fingerprint")
    previous = manifest_fixture(
        ManifestFixtureSpec(
            run_id="previous-run",
            source="uf",
            year=2024,
            status=BatchStatus.COMPLETED,
            completed_at=datetime(2025, 1, 1, tzinfo=UTC),
            identity=ContentIdentityFixture(
                query_hash=query.query_hash,
                schema_hash=query.schema_hash,
                fingerprint="old-fingerprint",
            ),
        )
    )
    store = InMemoryManifestStore((previous,))
    # When: it is planned again
    result = plan_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        query,
        store,
    )
    # Then: a distinct run is required
    assert result.status is BatchStatus.PLANNED
    assert result.run_id != store.manifests[0].run_id
