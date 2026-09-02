from uuid import NAMESPACE_URL, uuid5

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import CostLimitExceededError, SchemaDriftError
from alfabetizacao_pipeline.batch.models import (
    BatchEstimate,
    BatchPlan,
    BatchRequest,
    BatchStatus,
    BigQueryType,
    ContentFingerprint,
    QueryParameter,
    SourceInspection,
)
from alfabetizacao_pipeline.batch.ports import BigQueryPort, ManifestStore
from alfabetizacao_pipeline.batch.schema_drift import compare_schema
from alfabetizacao_pipeline.batch.sql import build_select_sql

SOURCE_PROJECT = "basedosdados"
SOURCE_DATASET = "br_inep_avaliacao_alfabetizacao"


def estimate_batch(
    request: BatchRequest,
    query: BigQueryPort,
    inspection: SourceInspection | None = None,
) -> BatchEstimate:
    """Inspect and price a partition without running a fingerprint query."""
    contract = SOURCE_CATALOG[request.source]
    source_inspection = inspection or query.inspect(request.source)
    drift = compare_schema(contract, source_inspection.columns)
    if drift.blocking:
        raise SchemaDriftError(source=request.source)
    select_sql = build_select_sql(contract, SOURCE_PROJECT, SOURCE_DATASET, request.year)
    parameters = (QueryParameter(name="year", data_type=BigQueryType.INT64, value=request.year),)
    estimate = query.dry_run(select_sql, parameters, request.maximum_bytes_billed)
    if estimate.bytes_processed > request.maximum_bytes_billed:
        raise CostLimitExceededError(
            estimated_bytes=estimate.bytes_processed,
            maximum_bytes_billed=request.maximum_bytes_billed,
        )
    return BatchEstimate(
        source=request.source,
        year=request.year,
        estimated_bytes=estimate.bytes_processed,
        maximum_bytes_billed=request.maximum_bytes_billed,
        query_hash=query.query_hash,
        schema_hash=query.schema_hash,
    )


def plan_batch(
    estimate: BatchEstimate,
    fingerprint: ContentFingerprint,
    manifests: ManifestStore,
) -> BatchPlan:
    """Resolve the idempotent decision from the exported snapshot identity."""
    previous = manifests.latest_completed(estimate.source, estimate.year)
    matching_previous = (
        previous is not None
        and previous.query_hash == estimate.query_hash
        and previous.schema_hash == estimate.schema_hash
        and previous.fingerprint == fingerprint.value
        and previous.row_count == fingerprint.row_count
    )
    status = BatchStatus.SKIPPED if matching_previous else BatchStatus.PLANNED
    run_key = (
        f"{estimate.source}:{estimate.year}:{estimate.query_hash}:"
        f"{estimate.schema_hash}:{fingerprint.value}:{fingerprint.row_count}"
    )
    return BatchPlan(
        run_id=str(uuid5(NAMESPACE_URL, run_key)),
        source=estimate.source,
        year=estimate.year,
        status=status,
        estimated_bytes=estimate.estimated_bytes,
        maximum_bytes_billed=estimate.maximum_bytes_billed,
        query_hash=estimate.query_hash,
        schema_hash=estimate.schema_hash,
        fingerprint=fingerprint.value,
        row_count=fingerprint.row_count,
    )
