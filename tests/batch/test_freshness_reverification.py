from datetime import UTC, datetime
from pathlib import Path

from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchRunContext,
    DryRunEstimate,
)
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime
from tests.batch.parquet_fixtures import parquet_payload


class SequenceClock:
    def __init__(self, values: tuple[datetime, ...]) -> None:
        self._values: list[datetime] = list(values)

    def now(self) -> datetime:
        return self._values.pop(0)


def test_identical_snapshot_reverification_preserves_original_completion(
    tmp_path: Path,
) -> None:
    landing = tmp_path / "landing.parquet"
    _ = landing.write_bytes(parquet_payload("uf", (1,)))
    objects = InMemoryObjectStore()
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    manifests = InMemoryManifestStore()
    query = FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1)
    original_started_at = datetime(2025, 1, 1, tzinfo=UTC)
    original_completed_at = datetime(2025, 1, 1, 0, 1, tzinfo=UTC)
    reverified_at = datetime(2025, 3, 1, 0, 1, tzinfo=UTC)
    clock = SequenceClock(
        (
            original_started_at,
            original_completed_at,
            datetime(2025, 3, 1, tzinfo=UTC),
            reverified_at,
        )
    )
    runtime = BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock)
    request = BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False)
    context = BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha="abc",
        image_digest="sha256:abc",
    )

    original = execute_batch(request, runtime, context)
    reverified = execute_batch(request, runtime, context)

    assert reverified.run_id == original.run_id
    assert reverified.completed_at == original_completed_at
    assert reverified.verified_at == reverified_at
    assert manifests.manifests[-1].completed_at == original_completed_at
    assert query.executed_queries == 2
