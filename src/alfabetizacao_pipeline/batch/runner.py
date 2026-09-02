from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Protocol, cast
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import LandingSchemaError
from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BatchRequest,
    BatchRunContext,
    BatchStatus,
    BigQueryType,
    ContentFingerprint,
    ObjectVersion,
    QueryParameter,
)
from alfabetizacao_pipeline.batch.planner import (
    SOURCE_DATASET,
    SOURCE_PROJECT,
    estimate_batch,
    plan_batch,
)
from alfabetizacao_pipeline.batch.sql import build_select_sql

if TYPE_CHECKING:
    from collections.abc import Iterator

    from alfabetizacao_pipeline.batch.runtime import BatchRuntime

FINGERPRINT_MODULUS = 1 << 256


class _ParquetBatchReader(Protocol):
    def iter_batches(self, *, batch_size: int) -> Iterator[pa.RecordBatch]: ...


def execute_batch(
    request: BatchRequest,
    runtime: BatchRuntime,
    context: BatchRunContext,
) -> BatchManifest:
    """Promote a snapshot only after validating every exported Parquet part."""
    inspection = runtime.query.inspect(request.source)
    estimate = estimate_batch(request, runtime.query, inspection)
    started_at = runtime.clock.now()
    identity = inspection.identity
    attempt_id = str(uuid4())
    contract = SOURCE_CATALOG[request.source]
    select_sql = build_select_sql(contract, SOURCE_PROJECT, SOURCE_DATASET, request.year)
    landing_uri = (
        f"{context.landing_prefix}/{request.source}/ano={request.year}/"
        f"attempt={attempt_id}/part-*.parquet"
    )
    snapshot = runtime.query.export_snapshot(
        select_sql,
        (QueryParameter(name="year", data_type=BigQueryType.INT64, value=request.year),),
        landing_uri,
        request.maximum_bytes_billed,
    )
    row_count = 0
    first_sum = 0
    second_sum = 0
    landing_parts: list[ObjectVersion] = []
    for uri in snapshot.object_uris:
        landing = runtime.objects.read_versioned(uri)
        part_count, part_first, part_second = _parquet_identity(landing.payload, contract.name)
        row_count += part_count
        first_sum = (first_sum + part_first) % FINGERPRINT_MODULUS
        second_sum = (second_sum + part_second) % FINGERPRINT_MODULUS
        landing_parts.append(landing.version)
    if row_count != snapshot.row_count:
        raise LandingSchemaError(source=contract.name)
    fingerprint = ContentFingerprint(
        row_count=row_count,
        value=f"sha256-multiset-v1:{first_sum:064x}:{second_sum:064x}",
    )
    plan = plan_batch(estimate, fingerprint, runtime.manifests)
    previous = runtime.manifests.latest_completed(request.source, request.year)
    if plan.status is BatchStatus.SKIPPED and previous is not None:
        return previous.model_copy(update={"verified_at": runtime.clock.now()})
    incomplete = BatchManifest(
        run_id=plan.run_id,
        attempt_id=attempt_id,
        source=request.source,
        year=request.year,
        status=BatchStatus.INCOMPLETE,
        source_identity=identity,
        row_count=plan.row_count,
        fingerprint=plan.fingerprint,
        query_hash=plan.query_hash,
        schema_hash=plan.schema_hash,
        bronze_objects=(),
        started_at=started_at,
        completed_at=None,
        verified_at=None,
        git_sha=context.git_sha,
        image_digest=context.image_digest,
    )
    runtime.manifests.persist(incomplete)
    bronze_objects = tuple(
        runtime.objects.copy_immutable(
            part,
            (
                f"{context.bronze_prefix}/{request.source}/ano={request.year}/"
                f"run={plan.run_id}/attempt={attempt_id}/part-{index:05d}.parquet"
            ),
        )
        for index, part in enumerate(landing_parts)
    )
    completed_at = runtime.clock.now()
    completed = incomplete.model_copy(
        update={
            "status": BatchStatus.COMPLETED,
            "bronze_objects": bronze_objects,
            "completed_at": completed_at,
            "verified_at": completed_at,
        }
    )
    runtime.manifests.persist(completed)
    return completed


def validate_landing_parquet(payload: bytes, source: str) -> bytes:
    """Reject landing files whose ordered schema or codec violates the contract."""
    _ = _validated_parquet_file(payload, source)
    return payload


def _validated_parquet_file(payload: bytes, source: str) -> pq.ParquetFile:
    parquet_file = pq.ParquetFile(pa.BufferReader(payload))
    contract = SOURCE_CATALOG[source]
    arrow_types: dict[BigQueryType, pa.DataType] = {
        BigQueryType.INT64: pa.int64(),
        BigQueryType.FLOAT64: pa.float64(),
        BigQueryType.STRING: pa.string(),
    }
    expected_schema = pa.schema(
        [
            pa.field(
                column.name,
                arrow_types[column.data_type],
                nullable=column.mode == "NULLABLE",
            )
            for column in contract.columns
        ]
    )
    metadata = parquet_file.metadata
    codecs = {
        metadata.row_group(group).column(column).compression.upper()
        for group in range(metadata.num_row_groups)
        for column in range(metadata.row_group(group).num_columns)
    }
    if not parquet_file.schema_arrow.equals(expected_schema) or codecs != {"SNAPPY"}:
        raise LandingSchemaError(source=source)
    return parquet_file


def _parquet_identity(payload: bytes, source: str) -> tuple[int, int, int]:
    parquet_file = _validated_parquet_file(payload, source)
    return _reader_identity(parquet_file, source)


def _reader_identity(reader: _ParquetBatchReader, source: str) -> tuple[int, int, int]:
    row_count = 0
    first_sum = 0
    second_sum = 0
    columns = SOURCE_CATALOG[source].columns
    for batch in reader.iter_batches(batch_size=65_536):
        row_count += batch.num_rows
        for row_index in range(batch.num_rows):
            row_hash = sha256()
            for column_index, source_column in enumerate(columns):
                name = source_column.name.encode()
                value = cast(
                    "pa.Scalar[pa.DataType]",
                    batch.column(column_index)[row_index],
                )
                if type(value) not in (
                    pa.Int64Scalar,
                    pa.DoubleScalar,
                    pa.StringScalar,
                ):
                    raise LandingSchemaError(source=source)
                encoded = b"" if not value.is_valid else str(value).encode()
                row_hash.update(len(name).to_bytes(2, byteorder="big"))
                row_hash.update(name)
                row_hash.update(source_column.data_type.value.encode())
                row_hash.update(b"\x00" if not value.is_valid else b"\x01")
                row_hash.update(len(encoded).to_bytes(8, byteorder="big"))
                row_hash.update(encoded)
            digest = row_hash.digest()
            first = sha256(b"\x01" + digest).digest()
            second = sha256(b"\x02" + digest).digest()
            first_sum = (first_sum + int.from_bytes(first, byteorder="big")) % FINGERPRINT_MODULUS
            second_sum = (
                second_sum + int.from_bytes(second, byteorder="big")
            ) % FINGERPRINT_MODULUS
    return row_count, first_sum, second_sum
