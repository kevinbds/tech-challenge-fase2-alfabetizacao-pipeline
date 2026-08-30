import pyarrow as pa
import pyarrow.parquet as pq

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import LandingSchemaError
from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BatchRequest,
    BatchRunContext,
    BatchStatus,
)
from alfabetizacao_pipeline.batch.planner import SOURCE_DATASET, SOURCE_PROJECT, plan_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime
from alfabetizacao_pipeline.batch.sql import build_export_sql, build_select_sql


def execute_batch(
    request: BatchRequest,
    runtime: BatchRuntime,
    context: BatchRunContext,
) -> BatchManifest:
    """Checkpoint, export and promote a validated immutable Bronze run."""
    plan = plan_batch(request, runtime.query, runtime.manifests)
    previous = runtime.manifests.latest_completed(request.source, request.year)
    if plan.status is BatchStatus.SKIPPED and previous is not None:
        return previous
    started_at = runtime.clock.now()
    identity = runtime.query.inspect(request.source).identity
    incomplete = BatchManifest(
        run_id=plan.run_id,
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
        git_sha=context.git_sha,
        image_digest=context.image_digest,
    )
    runtime.manifests.persist(incomplete)
    contract = SOURCE_CATALOG[request.source]
    select_sql = build_select_sql(contract, SOURCE_PROJECT, SOURCE_DATASET, request.year)
    landing_uri = (
        f"{context.landing_prefix}/{request.source}/ano={request.year}/"
        f"run={plan.run_id}/part-*.parquet"
    )
    exported = runtime.query.export(
        build_export_sql(select_sql, landing_uri),
        request.maximum_bytes_billed,
    )
    bronze_objects = tuple(
        runtime.objects.write_immutable(
            (
                f"{context.bronze_prefix}/{request.source}/ano={request.year}/"
                f"run={plan.run_id}/part-{index:05d}.parquet"
            ),
            _validated_parquet(runtime.objects.read(uri), contract.name),
        )
        for index, uri in enumerate(exported)
    )
    completed = incomplete.model_copy(
        update={
            "status": BatchStatus.COMPLETED,
            "bronze_objects": bronze_objects,
            "completed_at": runtime.clock.now(),
        }
    )
    runtime.manifests.persist(completed)
    return completed


def _validated_parquet(payload: bytes, source: str) -> bytes:
    parquet_file = pq.ParquetFile(pa.BufferReader(payload))
    expected_names = [column.name for column in SOURCE_CATALOG[source].columns]
    if parquet_file.schema_arrow.names != expected_names:
        raise LandingSchemaError(source=source)
    return payload
