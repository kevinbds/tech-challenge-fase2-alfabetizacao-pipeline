from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchRunContext,
    BatchStatus,
    DryRunEstimate,
    QueryParameter,
)
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime
from alfabetizacao_pipeline.schema_reference.builder import build_reference_file


class SequenceClock:
    def __init__(self, values: tuple[datetime, ...]) -> None:
        self._values: list[datetime] = list(values)

    def now(self) -> datetime:
        return self._values.pop(0)


class InterruptedBigQuery(FakeBigQuery):
    @override
    def export(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> tuple[str, ...]:
        del sql, parameters, destination_uri, maximum_bytes_billed
        raise InterruptedError


def test_runner_checkpoints_then_completes_immutable_bronze_when_executed(tmp_path: Path) -> None:
    # Given: valid local landing Parquet and deterministic runtime ports
    landing = tmp_path / "landing.parquet"
    _ = build_reference_file(SOURCE_CATALOG["uf"], landing)
    objects = InMemoryObjectStore()
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    manifests = InMemoryManifestStore()
    query = FakeBigQuery(DryRunEstimate(bytes_processed=1))
    clock = SequenceClock(
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
        )
    )
    # When: the batch state machine executes
    result = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock),
        BatchRunContext(
            landing_prefix="gs://landing",
            bronze_prefix="gs://bronze",
            git_sha="abc",
            image_digest="sha256:abc",
        ),
    )
    # Then: incomplete checkpoint precedes a completed immutable object
    assert tuple(manifest.status for manifest in manifests.manifests) == (
        BatchStatus.INCOMPLETE,
        BatchStatus.COMPLETED,
    )
    assert result.bronze_objects[0].generation == 1
    assert query.executed_queries == 1


def test_interruption_leaves_incomplete_checkpoint_when_export_stops() -> None:
    # Given: an export adapter interrupted after checkpoint persistence
    manifests = InMemoryManifestStore()
    query = InterruptedBigQuery(DryRunEstimate(bytes_processed=1))
    runtime = BatchRuntime(
        query=query,
        manifests=manifests,
        objects=InMemoryObjectStore(),
        clock=SequenceClock((datetime(2025, 1, 1, tzinfo=UTC),)),
    )
    # When: the interrupt signal reaches the export adapter
    with pytest.raises(InterruptedError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            runtime,
            BatchRunContext(
                landing_prefix="gs://landing",
                bronze_prefix="gs://bronze",
                git_sha="abc",
                image_digest="sha256:abc",
            ),
        )
    # Then: no partial promotion is recorded
    assert tuple(manifest.status for manifest in manifests.manifests) == (BatchStatus.INCOMPLETE,)
