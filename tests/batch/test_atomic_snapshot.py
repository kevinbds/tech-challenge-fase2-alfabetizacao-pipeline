from datetime import UTC, datetime
from typing import override

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    LandingSchemaError,
    StaleObjectGenerationError,
)
from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchRunContext,
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
    VersionedPayload,
)
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime
from tests.batch.parquet_fixtures import parquet_payload


class SequenceClock:
    def __init__(self, values: tuple[datetime, ...]) -> None:
        self._values: list[datetime] = list(values)

    def now(self) -> datetime:
        return self._values.pop(0)


class ChangingBoundaryQuery(FakeBigQuery):
    def __init__(self) -> None:
        super().__init__(DryRunEstimate(bytes_processed=1))
        self._attempt: int = 0

    @override
    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        del sql, parameters, maximum_bytes_billed
        self._attempt += 1
        self.export_destinations.append(destination_uri)
        if self._attempt == 1:
            return SnapshotExport(
                row_count=2,
                object_uris=("gs://landing/first.parquet", "gs://landing/second.parquet"),
            )
        return SnapshotExport(row_count=2, object_uris=("gs://landing/combined.parquet",))


class FailSecondBronzeOnce(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self._failed: bool = False

    @override
    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        if destination_uri.endswith("part-00001.parquet") and not self._failed:
            self._failed = True
            raise InterruptedError
        return super().copy_immutable(source, destination_uri)


class CountingObjectStore(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads: dict[str, int] = {}

    @override
    def read_versioned(self, uri: str) -> VersionedPayload:
        self.reads[uri] = self.reads.get(uri, 0) + 1
        return super().read_versioned(uri)


class ChangeSourceBeforeCopy(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.changed: bool = False

    @override
    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        if not self.changed:
            self.changed = True
            self.seed(source.uri, parquet_payload("uf", (99,)))
        return super().copy_immutable(source, destination_uri)


def _context() -> BatchRunContext:
    return BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha="abc",
        image_digest="sha256:abc",
    )


def _execute(payload: bytes) -> str:
    return _execute_parts((payload,))


def _execute_parts(payloads: tuple[bytes, ...]) -> str:
    objects = InMemoryObjectStore()
    uris = tuple(f"gs://landing/part-{index}.parquet" for index in range(len(payloads)))
    for uri, payload in zip(uris, payloads, strict=True):
        objects.seed(uri, payload)
    row_count = sum(
        pq.ParquetFile(pa.BufferReader(payload)).metadata.num_rows for payload in payloads
    )
    result = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(
            query=FakeBigQuery(
                DryRunEstimate(bytes_processed=1),
                snapshot_row_count=row_count,
                snapshot_uris=uris,
            ),
            manifests=InMemoryManifestStore(),
            objects=objects,
            clock=SequenceClock(
                (
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
                )
            ),
        ),
        _context(),
    )
    assert result.row_count == row_count
    return result.fingerprint


def test_manifest_identity_is_derived_from_exported_snapshot() -> None:
    first = parquet_payload("uf", (1, 2))
    second = parquet_payload("uf", (3, 4))

    first_fingerprint = _execute(first)
    second_fingerprint = _execute(second)

    assert first_fingerprint != second_fingerprint


def test_fingerprint_is_independent_of_row_order_and_file_boundaries() -> None:
    split = (
        parquet_payload("uf", (1,)),
        parquet_payload("uf", (2, 3)),
    )
    reordered = (parquet_payload("uf", (3, 1, 2)),)

    assert _execute_parts(split) == _execute_parts(reordered)


def test_equal_count_even_multiplicity_changes_fingerprint() -> None:
    first = parquet_payload("uf", (1, 1, 2, 2))
    second = parquet_payload("uf", (3, 3, 4, 4))

    first_fingerprint = _execute(first)
    second_fingerprint = _execute(second)

    assert first_fingerprint != second_fingerprint


def test_retry_with_different_file_boundaries_uses_isolated_bronze_attempt() -> None:
    first = parquet_payload("uf", (1,))
    second = parquet_payload("uf", (2,))
    combined = parquet_payload("uf", (1, 2))
    objects = FailSecondBronzeOnce()
    objects.seed("gs://landing/first.parquet", first)
    objects.seed("gs://landing/second.parquet", second)
    objects.seed("gs://landing/combined.parquet", combined)
    manifests = InMemoryManifestStore()
    query = ChangingBoundaryQuery()
    runtime = BatchRuntime(
        query=query,
        manifests=manifests,
        objects=objects,
        clock=SequenceClock(
            (
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
            )
        ),
    )
    request = BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False)
    with pytest.raises(InterruptedError):
        _ = execute_batch(request, runtime, _context())

    try:
        completed = execute_batch(request, runtime, _context())
    except ImmutableObjectExistsError as error:
        pytest.fail(f"retry colidiu com Bronze parcial: {error}")

    assert completed.attempt_id is not None
    assert completed.bronze_objects
    assert all(f"/attempt={completed.attempt_id}/" in item.uri for item in completed.bronze_objects)
    assert len({item.uri for item in completed.bronze_objects}) == len(completed.bronze_objects)


def test_each_landing_part_is_downloaded_once() -> None:
    first_uri = "gs://landing/first.parquet"
    second_uri = "gs://landing/second.parquet"
    objects = CountingObjectStore()
    objects.seed(first_uri, parquet_payload("uf", (1,)))
    objects.seed(second_uri, parquet_payload("uf", (2,)))
    query = FakeBigQuery(
        DryRunEstimate(bytes_processed=1),
        snapshot_row_count=2,
        snapshot_uris=(first_uri, second_uri),
    )

    _ = execute_batch(
        BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
        BatchRuntime(
            query=query,
            manifests=InMemoryManifestStore(),
            objects=objects,
            clock=SequenceClock(
                (
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
                )
            ),
        ),
        _context(),
    )

    assert objects.reads == {first_uri: 1, second_uri: 1}


def test_snapshot_count_must_match_exported_parquet() -> None:
    objects = InMemoryObjectStore()
    objects.seed("gs://landing/fixture.parquet", parquet_payload("uf", (1, 2)))
    manifests = InMemoryManifestStore()

    with pytest.raises(LandingSchemaError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            BatchRuntime(
                query=FakeBigQuery(
                    DryRunEstimate(bytes_processed=1),
                    snapshot_row_count=3,
                ),
                manifests=manifests,
                objects=objects,
                clock=SequenceClock((datetime(2025, 1, 1, tzinfo=UTC),)),
            ),
            _context(),
        )

    assert not manifests.manifests
    assert not any(uri.startswith("gs://bronze/") for uri in objects.objects)


def test_source_generation_change_before_copy_fails_closed() -> None:
    payload = parquet_payload("uf", (1,))
    objects = ChangeSourceBeforeCopy()
    objects.seed("gs://landing/fixture.parquet", payload)

    with pytest.raises(StaleObjectGenerationError):
        _ = execute_batch(
            BatchRequest(source="uf", year=2024, maximum_bytes_billed=25, dry_run=False),
            BatchRuntime(
                query=FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1),
                manifests=InMemoryManifestStore(),
                objects=objects,
                clock=SequenceClock((datetime(2025, 1, 1, tzinfo=UTC),)),
            ),
            _context(),
        )

    assert not any(uri.startswith("gs://bronze/") for uri in objects.objects)
