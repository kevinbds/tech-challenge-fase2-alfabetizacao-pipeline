from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest

from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchRunContext,
    BatchStatus,
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
)
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime
from tests.batch.parquet_fixtures import parquet_payload


class SequenceClock:
    def __init__(self, values: tuple[datetime, ...]) -> None:
        self._values: list[datetime] = list(values)

    def now(self) -> datetime:
        return self._values.pop(0)


class InterruptedBigQuery(FakeBigQuery):
    @override
    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        del sql, parameters, destination_uri, maximum_bytes_billed
        raise InterruptedError


class TwoPartBigQuery(FakeBigQuery):
    @override
    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        del sql, parameters, maximum_bytes_billed
        self.executed_queries: int = self.executed_queries + 1
        self.export_destinations.append(destination_uri)
        return SnapshotExport(
            row_count=2,
            object_uris=("gs://landing/first.parquet", "gs://landing/second.parquet"),
        )


class FailBeforeBronzeOnce(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.failed: bool = False

    @override
    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        if not self.failed:
            self.failed = True
            raise InterruptedError
        return super().copy_immutable(source, destination_uri)


class FailSecondBronzeOnce(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.failed: bool = False

    @override
    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        if destination_uri.endswith("part-00001.parquet") and not self.failed:
            self.failed = True
            raise InterruptedError
        return super().copy_immutable(source, destination_uri)


def test_runner_checkpoints_then_completes_immutable_bronze_when_executed(tmp_path: Path) -> None:
    landing = tmp_path / "landing.parquet"
    _ = landing.write_bytes(parquet_payload("uf", (1,)))
    objects = InMemoryObjectStore()
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    manifests = InMemoryManifestStore()
    query = FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1)
    clock = SequenceClock(
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
        )
    )
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
    assert tuple(manifest.status for manifest in manifests.manifests) == (
        BatchStatus.INCOMPLETE,
        BatchStatus.COMPLETED,
    )
    assert result.bronze_objects[0].generation == 1
    assert query.executed_queries == 1
    assert query.inspect_calls == 1


def test_interruption_before_snapshot_leaves_no_incomplete_checkpoint() -> None:
    manifests = InMemoryManifestStore()
    query = InterruptedBigQuery(DryRunEstimate(bytes_processed=1))
    runtime = BatchRuntime(
        query=query,
        manifests=manifests,
        objects=InMemoryObjectStore(),
        clock=SequenceClock((datetime(2025, 1, 1, tzinfo=UTC),)),
    )
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
    assert not manifests.manifests


def test_retry_completes_after_checkpoint_interruption(tmp_path: Path) -> None:
    manifests = InMemoryManifestStore()
    objects = InMemoryObjectStore()
    interrupted = InterruptedBigQuery(DryRunEstimate(bytes_processed=1))
    clock = SequenceClock(
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
        )
    )
    context = BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha="abc",
        image_digest="sha256:abc",
    )
    with pytest.raises(InterruptedError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            BatchRuntime(query=interrupted, manifests=manifests, objects=objects, clock=clock),
            context,
        )
    landing = tmp_path / "landing.parquet"
    _ = landing.write_bytes(parquet_payload("uf", (1,)))
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    result = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(
            query=FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1),
            manifests=manifests,
            objects=objects,
            clock=clock,
        ),
        context,
    )
    assert result.status is BatchStatus.COMPLETED
    assert tuple(manifest.status for manifest in manifests.manifests) == (
        BatchStatus.INCOMPLETE,
        BatchStatus.COMPLETED,
    )


def test_retry_completes_after_landing_without_reusing_landing_attempt_uri(tmp_path: Path) -> None:
    landing = tmp_path / "landing.parquet"
    _ = landing.write_bytes(parquet_payload("uf", (1,)))
    objects = FailBeforeBronzeOnce()
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    manifests = InMemoryManifestStore()
    query = FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1)
    clock = SequenceClock(
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
        )
    )
    context = BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha="abc",
        image_digest="sha256:abc",
    )
    with pytest.raises(InterruptedError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock),
            context,
        )
    result = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock),
        context,
    )
    assert result.status is BatchStatus.COMPLETED
    assert len(set(query.export_destinations)) == 2
    assert all("/attempt=" in uri for uri in query.export_destinations)


def test_retry_isolates_first_bronze_after_second_bronze_interruption(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    _ = first.write_bytes(parquet_payload("uf", (1,)))
    _ = second.write_bytes(parquet_payload("uf", (2,)))
    objects = FailSecondBronzeOnce()
    objects.seed("gs://landing/first.parquet", first.read_bytes())
    objects.seed("gs://landing/second.parquet", second.read_bytes())
    manifests = InMemoryManifestStore()
    query = TwoPartBigQuery(DryRunEstimate(bytes_processed=1))
    clock = SequenceClock(
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
            datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
        )
    )
    context = BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha="abc",
        image_digest="sha256:abc",
    )
    with pytest.raises(InterruptedError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock),
            context,
        )
    result = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(query=query, manifests=manifests, objects=objects, clock=clock),
        context,
    )
    assert result.status is BatchStatus.COMPLETED
    assert objects.created_objects == 3
    assert objects.reused_objects == 0
