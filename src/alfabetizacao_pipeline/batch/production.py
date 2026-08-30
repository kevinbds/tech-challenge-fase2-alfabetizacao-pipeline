from dataclasses import dataclass

from alfabetizacao_pipeline.batch.adapters import (
    BigQueryAdapter,
    BigQueryAdapterConfig,
    BigQuerySdkBoundary,
    GcsObjectStore,
    GcsSdkBoundary,
    SourceLocator,
)
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.google_bigquery import GoogleBigQuerySdk
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk
from alfabetizacao_pipeline.batch.manifest_store import GcsManifestStore
from alfabetizacao_pipeline.batch.models import BatchRunContext
from alfabetizacao_pipeline.batch.planner import SOURCE_DATASET, SOURCE_PROJECT
from alfabetizacao_pipeline.batch.runtime import BatchRuntime, SystemClock
from alfabetizacao_pipeline.batch.sql import build_select_sql, schema_hash, stable_hash
from alfabetizacao_pipeline.config import AppSettings


@dataclass(frozen=True, slots=True)
class ProductionComposition:
    """Authenticated runtime and immutable deployment context."""

    runtime: BatchRuntime
    context: BatchRunContext


@dataclass(frozen=True, slots=True)
class ProductionDependencies:
    """Injectable SDK boundaries for deterministic composition tests."""

    storage: GcsSdkBoundary
    query: BigQuerySdkBoundary


def build_production_composition(
    source: str,
    settings: AppSettings,
    *,
    git_sha: str,
    image_digest: str,
    dependencies: ProductionDependencies | None = None,
) -> ProductionComposition:
    """Wire Google SDK adapters without fixture fallbacks."""
    contract = SOURCE_CATALOG[source]
    storage = (
        dependencies.storage if dependencies is not None else GoogleGcsSdk(settings.gcp_project_id)
    )
    query_sdk = (
        dependencies.query
        if dependencies is not None
        else GoogleBigQuerySdk(settings.gcp_project_id, storage)
    )
    canonical_query = build_select_sql(contract, SOURCE_PROJECT, SOURCE_DATASET, 2000)
    query = BigQueryAdapter(
        BigQueryAdapterConfig(
            locator=SourceLocator(SOURCE_PROJECT, SOURCE_DATASET, source),
            query_hash=stable_hash(canonical_query),
            schema_hash=schema_hash(contract),
        ),
        query_sdk,
    )
    landing_prefix = f"gs://{settings.gcp_project_id}-landing/batch"
    bronze_prefix = f"gs://{settings.gcp_project_id}-bronze/batch"
    manifest_prefix = f"gs://{settings.gcp_project_id}-control/manifests"
    return ProductionComposition(
        runtime=BatchRuntime(
            query=query,
            manifests=GcsManifestStore(manifest_prefix, storage),
            objects=GcsObjectStore(storage),
            clock=SystemClock(),
        ),
        context=BatchRunContext(
            landing_prefix=landing_prefix,
            bronze_prefix=bronze_prefix,
            git_sha=git_sha,
            image_digest=image_digest,
        ),
    )
