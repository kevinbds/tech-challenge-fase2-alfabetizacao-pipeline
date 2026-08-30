from uuid import NAMESPACE_URL, uuid5

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import CostLimitExceededError, SchemaDriftError
from alfabetizacao_pipeline.batch.models import (
    BatchPlan,
    BatchRequest,
    BatchStatus,
    BigQueryType,
    QueryParameter,
)
from alfabetizacao_pipeline.batch.ports import BigQueryPort, ManifestStore
from alfabetizacao_pipeline.batch.schema_drift import compare_schema
from alfabetizacao_pipeline.batch.sql import build_fingerprint_sql, build_select_sql

SOURCE_PROJECT = "basedosdados"
SOURCE_DATASET = "br_inep_avaliacao_alfabetizacao"


def plan_batch(
    request: BatchRequest,
    query: BigQueryPort,
    manifests: ManifestStore,
) -> BatchPlan:
    """Inspect, dry-run and fingerprint a partition without cloud writes."""
    contract = SOURCE_CATALOG[request.source]
    inspection = query.inspect(request.source)
    drift = compare_schema(contract, inspection.columns)
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
    fingerprint_sql = build_fingerprint_sql(contract, SOURCE_PROJECT, SOURCE_DATASET, request.year)
    fingerprint = query.compute_fingerprint(
        fingerprint_sql,
        parameters,
        request.maximum_bytes_billed,
    )
    previous = manifests.latest_completed(request.source, request.year)
    matching_previous = (
        previous is not None
        and previous.query_hash == query.query_hash
        and previous.schema_hash == query.schema_hash
        and previous.fingerprint == fingerprint.value
    )
    status = BatchStatus.SKIPPED if matching_previous else BatchStatus.PLANNED
    run_key = (
        f"{request.source}:{request.year}:{query.query_hash}:"
        f"{query.schema_hash}:{fingerprint.value}"
    )
    return BatchPlan(
        run_id=str(uuid5(NAMESPACE_URL, run_key)),
        source=request.source,
        year=request.year,
        status=status,
        estimated_bytes=estimate.bytes_processed,
        maximum_bytes_billed=request.maximum_bytes_billed,
        query_hash=query.query_hash,
        schema_hash=query.schema_hash,
        fingerprint=fingerprint.value,
        row_count=fingerprint.row_count,
    )
