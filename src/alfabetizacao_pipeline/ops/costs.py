from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Annotated, Final, override

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline.errors import ExitCode
from alfabetizacao_pipeline.ops.models import (
    CostCatalog,
    CostReport,
    Currency,
    InvalidCostResponse,
)
from alfabetizacao_pipeline.types import OutputFormat

DEFAULT_CATALOG = Path("ops/cost_profiles.yml")
TIB = Decimal(1024**4)
CENT = Decimal("0.01")
WORKFLOW_STEP_BLOCK: Final = 1000


@dataclass(frozen=True, slots=True)
class ProfileNotFoundError(Exception):
    """Carry the rejected profile name into the stable CLI error response."""

    profile: str

    @override
    def __str__(self) -> str:
        return f"cost profile not found: {self.profile}"


app = typer.Typer(
    name="costs",
    help="Estima o custo local com premissas versionadas, sem acessar a nuvem.",
    no_args_is_help=True,
    rich_markup_mode=None,
)


@app.callback()
def main() -> None:
    """Register the cost command group without performing I/O."""


def load_catalog(path: Path) -> CostCatalog:
    """Reject malformed or unknown pricing fields at the file boundary."""
    return CostCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def estimate_profile(catalog: CostCatalog, profile_name: str) -> CostReport:
    """Calculate rounded BRL components without external price lookups."""
    try:
        request = catalog.profiles[profile_name]
    except KeyError as error:
        raise ProfileNotFoundError(profile=profile_name) from error

    bigquery = _money(
        Decimal(request.bigquery_total_bytes_processed) / TIB * catalog.rates.bigquery_per_tib
    )
    bigquery_storage_write_api = _money(
        request.bigquery_storage_write_api_gib * catalog.rates.bigquery_storage_write_api_per_gib
    )
    bigquery_active_storage = _money(
        request.bigquery_active_storage_gib_month
        * catalog.rates.bigquery_active_storage_per_gib_month
    )
    dataflow_vcpu = _money(
        Decimal(request.dataflow_max_workers)
        * Decimal(request.dataflow_worker_vcpus)
        * request.dataflow_runtime_hours
        * catalog.rates.dataflow_vcpu_per_hour
    )
    dataflow_memory = _money(
        Decimal(request.dataflow_max_workers)
        * request.dataflow_worker_memory_gib
        * request.dataflow_runtime_hours
        * catalog.rates.dataflow_memory_per_gib_hour
    )
    dataflow_persistent_disk = _money(
        Decimal(request.dataflow_max_workers)
        * request.dataflow_disk_gib
        * request.dataflow_runtime_hours
        * catalog.rates.dataflow_standard_pd_per_gib_hour
    )
    dataflow_streaming_engine = _money(
        request.dataflow_streaming_engine_compute_unit_hours
        * catalog.rates.dataflow_streaming_engine_compute_unit_hour
    )
    dataflow = _money(
        dataflow_vcpu + dataflow_memory + dataflow_persistent_disk + dataflow_streaming_engine
    )
    gcs_storage = _money(request.gcs_storage_gib_month * catalog.rates.gcs_storage_per_gib_month)
    gcs_replication = _money(
        request.gcs_replication_written_gib * catalog.rates.gcs_replication_per_gib
    )
    gcs_class_a_operations = _money(
        request.gcs_class_a_operations_per_1000 * catalog.rates.gcs_class_a_operations_per_1000
    )
    gcs_class_b_operations = _money(
        request.gcs_class_b_operations_per_1000 * catalog.rates.gcs_class_b_operations_per_1000
    )
    storage = _money(
        gcs_storage + gcs_replication + gcs_class_a_operations + gcs_class_b_operations
    )
    pubsub_publish_delivery = _money(
        request.pubsub_publish_delivery_gib * catalog.rates.pubsub_publish_delivery_per_gib
    )
    pubsub_gcs_export = _money(
        request.pubsub_gcs_export_gib * catalog.rates.pubsub_gcs_export_per_gib
    )
    pubsub_retention = _money(
        request.pubsub_retained_gib_month * catalog.rates.pubsub_retention_per_gib_month
    )
    pubsub = _money(pubsub_publish_delivery + pubsub_gcs_export + pubsub_retention)
    cloud_run = _money(
        request.cloud_run_vcpu_seconds * catalog.rates.cloud_run_vcpu_second
        + request.cloud_run_gib_seconds * catalog.rates.cloud_run_gib_second
    )
    workflows = _money(
        Decimal((request.workflows_internal_steps + WORKFLOW_STEP_BLOCK - 1) // WORKFLOW_STEP_BLOCK)
        * catalog.rates.workflows_internal_steps_per_1000
    )
    scheduler = _money(request.scheduler_jobs_month * catalog.rates.scheduler_per_job_month)
    artifact_registry = _money(
        request.artifact_registry_gib_month * catalog.rates.artifact_registry_per_gib_month
    )
    cloud_build_build_images = _money(
        request.cloud_build_build_images_minutes * catalog.rates.cloud_build_build_images_per_minute
    )
    cloud_build_verify_images = _money(
        request.cloud_build_verify_images_minutes
        * catalog.rates.cloud_build_verify_images_per_minute
    )
    cloud_build = _money(cloud_build_build_images + cloud_build_verify_images)
    logging = _money(request.logging_gib * catalog.rates.logging_per_gib)
    monitoring = _money(request.monitoring_mib * catalog.rates.monitoring_per_mib)
    network_egress = _money(request.network_egress_gib * catalog.rates.network_egress_per_gib)
    cross_region_data_transfer = _money(
        request.cross_region_data_transfer_gib * catalog.rates.cross_region_data_transfer_per_gib
    )
    total = _money(
        bigquery
        + bigquery_storage_write_api
        + bigquery_active_storage
        + dataflow
        + storage
        + pubsub
        + cloud_run
        + workflows
        + scheduler
        + artifact_registry
        + cloud_build
        + logging
        + monitoring
        + network_egress
        + cross_region_data_transfer
    )
    return CostReport(
        profile=profile_name,
        currency=request.currency,
        bigquery_location=catalog.bigquery_location,
        runtime_location=catalog.runtime_location,
        storage_location=catalog.storage_location,
        bigquery=bigquery,
        bigquery_storage_write_api=bigquery_storage_write_api,
        bigquery_active_storage=bigquery_active_storage,
        dataflow=dataflow,
        dataflow_vcpu=dataflow_vcpu,
        dataflow_memory=dataflow_memory,
        dataflow_persistent_disk=dataflow_persistent_disk,
        dataflow_streaming_engine=dataflow_streaming_engine,
        storage=storage,
        gcs_storage=gcs_storage,
        gcs_replication=gcs_replication,
        gcs_class_a_operations=gcs_class_a_operations,
        gcs_class_b_operations=gcs_class_b_operations,
        pubsub=pubsub,
        pubsub_publish_delivery=pubsub_publish_delivery,
        pubsub_gcs_export=pubsub_gcs_export,
        pubsub_retention=pubsub_retention,
        cloud_run=cloud_run,
        workflows=workflows,
        scheduler=scheduler,
        artifact_registry=artifact_registry,
        cloud_build=cloud_build,
        cloud_build_build_images=cloud_build_build_images,
        cloud_build_verify_images=cloud_build_verify_images,
        logging=logging,
        monitoring=monitoring,
        network_egress=network_egress,
        cross_region_data_transfer=cross_region_data_transfer,
        total=total,
        usd_to_brl=catalog.usd_to_brl,
        usd_to_brl_as_of=catalog.usd_to_brl_as_of,
        rate_basis=catalog.rate_basis,
        bigquery_query_count=request.bigquery_query_count,
        max_bytes_billed_per_query=request.bigquery_max_bytes_billed_per_query,
    )


@app.command("estimate")
def estimate(
    profile: Annotated[str, typer.Option("--profile", min=1)] = "demo",
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
    currency: Annotated[Currency | None, typer.Option("--currency")] = None,
    catalog_path: Annotated[Path, typer.Option("--catalog", exists=True)] = DEFAULT_CATALOG,
) -> None:
    """Emit deterministic JSON and map invalid input to the stable CLI exit code."""
    try:
        catalog = load_catalog(catalog_path)
        report = estimate_profile(catalog, profile)
    except ValidationError as error:
        response = InvalidCostResponse(
            error_code="invalid_cost_catalog",
            error_count=error.error_count(),
        )
        typer.echo(response.model_dump_json(), err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error
    except ProfileNotFoundError as error:
        response = InvalidCostResponse(error_code="profile_not_found", error_count=1)
        typer.echo(response.model_dump_json(), err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error

    if currency is not None and currency is not report.currency:
        typer.echo('{"status":"invalid","error":"currency mismatch"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION)
    typer.echo(report.model_dump_json())


if __name__ == "__main__":
    app()
