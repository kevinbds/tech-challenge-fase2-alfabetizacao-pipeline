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
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchStatus,
    ContentFingerprint,
    DryRunEstimate,
)
from alfabetizacao_pipeline.batch.planner import estimate_batch, plan_batch


@pytest.mark.parametrize(("estimated", "blocked"), [(24, False), (25, False), (26, True)])
def test_cost_cap_blocks_only_above_limit_when_estimating(estimated: int, blocked: bool) -> None:
    query = FakeBigQuery(estimate=DryRunEstimate(bytes_processed=estimated))
    request = BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=True)
    if blocked:
        with pytest.raises(CostLimitExceededError):
            _ = estimate_batch(request, query)
        assert query.executed_queries == 0
    else:
        result = estimate_batch(request, query)
        assert result.status is BatchStatus.PLANNED
        assert query.executed_queries == 0


def test_skip_requires_query_schema_and_fingerprint_match_when_planning() -> None:
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
                fingerprint="fixture-fingerprint",
            ),
        )
    ).model_copy(update={"row_count": 10})
    store = InMemoryManifestStore((previous,))
    estimate = estimate_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        query,
    )
    result = plan_batch(
        estimate,
        ContentFingerprint(row_count=10, value="fixture-fingerprint"),
        store,
    )
    assert result.status is BatchStatus.SKIPPED


def test_changed_fingerprint_creates_new_run_when_replanned() -> None:
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
                fingerprint="old-fingerprint",
            ),
        )
    )
    store = InMemoryManifestStore((previous,))
    estimate = estimate_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        query,
    )
    result = plan_batch(
        estimate,
        ContentFingerprint(row_count=1, value="new-fingerprint"),
        store,
    )
    assert result.status is BatchStatus.PLANNED
    assert result.run_id != store.manifests[0].run_id


def test_same_xor_with_changed_row_count_cannot_skip_or_reuse_run_id() -> None:
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
                fingerprint="fixture-fingerprint",
            ),
        )
    ).model_copy(update={"row_count": 20})

    estimate = estimate_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        query,
    )
    result = plan_batch(
        estimate,
        ContentFingerprint(row_count=10, value="fixture-fingerprint"),
        InMemoryManifestStore((previous,)),
    )

    assert result.status is BatchStatus.PLANNED
    assert result.run_id != previous.run_id
