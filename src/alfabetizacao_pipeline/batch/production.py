import os
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
from alfabetizacao_pipeline.batch.release_models import StorageLocations
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


def load_storage_locations() -> StorageLocations:
    """Parse Terraform-provided GCS locations at the process boundary."""
    return StorageLocations.model_validate(
        {
            "landing_prefix": os.environ.get("ALFABETIZACAO_LANDING_PREFIX"),
            "bronze_prefix": os.environ.get("ALFABETIZACAO_BRONZE_PREFIX"),
            "manifest_prefix": os.environ.get("ALFABETIZACAO_MANIFEST_PREFIX"),
        }
    )


def build_production_composition(
    source: str,
    settings: AppSettings,
    *,
    git_sha: str,
    image_digest: str,
    dependencies: ProductionDependencies | None = None,
) -> ProductionComposition:
    """Wire Google SDK adapters without fixture fallbacks."""
    query = build_production_query(source, settings, dependencies=dependencies)
    storage = (
        dependencies.storage if dependencies is not None else GoogleGcsSdk(settings.gcp_project_id)
    )
    locations = load_storage_locations()
    return ProductionComposition(
        runtime=BatchRuntime(
            query=query,
            manifests=GcsManifestStore(locations.manifest_prefix, storage),
            objects=GcsObjectStore(storage),
            clock=SystemClock(),
        ),
        context=BatchRunContext(
            landing_prefix=locations.landing_prefix,
            bronze_prefix=locations.bronze_prefix,
            git_sha=git_sha,
            image_digest=image_digest,
        ),
    )


def build_production_query(
    source: str,
    settings: AppSettings,
    *,
    dependencies: ProductionDependencies | None = None,
) -> BigQueryAdapter:
    """Build the read-only query boundary without requiring provisioned GCS locations."""
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
    return BigQueryAdapter(
        BigQueryAdapterConfig(
            locator=SourceLocator(SOURCE_PROJECT, SOURCE_DATASET, source),
            query_hash=stable_hash(canonical_query),
            schema_hash=schema_hash(contract),
        ),
        query_sdk,
    )
