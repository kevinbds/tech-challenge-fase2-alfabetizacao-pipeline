from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from alfabetizacao_pipeline.ops.costs import app, estimate_profile, load_catalog
from alfabetizacao_pipeline.ops.models import CostRequest, Currency, InvalidCostResponse

CATALOG = Path("ops/cost_profiles.yml")


def test_demo_cost_when_profile_is_estimated() -> None:
    catalog = load_catalog(CATALOG)

    report = estimate_profile(catalog, "demo")

    assert report.currency is Currency.BRL
    assert catalog.bigquery_location == "US"
    assert catalog.runtime_location == "us-central1"
    assert catalog.storage_location == "us-central1"
    assert report.bigquery_location == "US"
    assert report.runtime_location == "us-central1"
    assert report.storage_location == "us-central1"
    assert catalog.profiles["demo"].bigquery_total_bytes_processed == 375 * 1024**3
    assert catalog.profiles["demo"].bigquery_query_count == 243
    assert catalog.profiles["demo"].bigquery_max_bytes_billed_per_query == 25 * 1024**3
    assert catalog.profiles["demo"].bigquery_storage_write_api_gib == Decimal("0.01")
    assert catalog.profiles["demo"].bigquery_active_storage_gib_month == Decimal(1)
    assert catalog.profiles["demo"].pubsub_retained_gib_month == Decimal("0.000333333")
    assert catalog.profiles["demo"].cloud_run_vcpu_seconds == Decimal(780)
    assert catalog.profiles["demo"].cloud_run_gib_seconds == Decimal(1470)

    expected_rates = (
        (catalog.rates.bigquery_storage_write_api_per_gib, Decimal("0.1375")),
        (catalog.rates.bigquery_active_storage_per_gib_month, Decimal("0.1265")),
        (catalog.rates.cloud_run_vcpu_second, Decimal("0.000099")),
        (catalog.rates.cloud_run_gib_second, Decimal("0.000011")),
        (catalog.rates.dataflow_vcpu_per_hour, Decimal("0.3795")),
        (catalog.rates.dataflow_memory_per_gib_hour, Decimal("0.0195635")),
        (catalog.rates.dataflow_standard_pd_per_gib_hour, Decimal("0.000297")),
        (catalog.rates.dataflow_streaming_engine_compute_unit_hour, Decimal("0.4895")),
        (catalog.rates.pubsub_publish_delivery_per_gib, Decimal("0.21484375")),
        (catalog.rates.pubsub_gcs_export_per_gib, Decimal("0.2685546875")),
        (catalog.rates.pubsub_retention_per_gib_month, Decimal("1.485")),
        (catalog.rates.gcs_storage_per_gib_month, Decimal("0.11")),
        (catalog.rates.gcs_replication_per_gib, Decimal("0.11")),
        (catalog.rates.gcs_class_a_operations_per_1000, Decimal("0.0275")),
        (catalog.rates.gcs_class_b_operations_per_1000, Decimal("0.0022")),
        (catalog.rates.workflows_internal_steps_per_1000, Decimal("0.055")),
        (catalog.rates.cloud_build_build_images_per_minute, Decimal("0.0858")),
        (catalog.rates.cloud_build_verify_images_per_minute, Decimal("0.033")),
        (catalog.rates.network_egress_per_gib, Decimal("1.045")),
        (catalog.rates.cross_region_data_transfer_per_gib, Decimal("0.77")),
    )
    assert all(actual == expected for actual, expected in expected_rates)

    expected_components = (
        (report.bigquery, Decimal("12.59")),
        (report.bigquery_storage_write_api, Decimal("0.00")),
        (report.bigquery_active_storage, Decimal("0.13")),
        (report.dataflow, Decimal("2.69")),
        (report.dataflow_vcpu, Decimal("1.77")),
        (report.dataflow_memory, Decimal("0.34")),
        (report.dataflow_persistent_disk, Decimal("0.01")),
        (report.dataflow_streaming_engine, Decimal("0.57")),
        (report.storage, Decimal("0.17")),
        (report.gcs_storage, Decimal("0.14")),
        (report.gcs_replication, Decimal("0.00")),
        (report.gcs_class_a_operations, Decimal("0.03")),
        (report.gcs_class_b_operations, Decimal("0.00")),
        (report.pubsub, Decimal("0.00")),
        (report.pubsub_publish_delivery, Decimal("0.00")),
        (report.pubsub_gcs_export, Decimal("0.00")),
        (report.pubsub_retention, Decimal("0.00")),
        (report.cloud_run, Decimal("0.09")),
        (report.workflows, Decimal("0.28")),
        (report.scheduler, Decimal("0.55")),
        (report.artifact_registry, Decimal("0.28")),
        (report.cloud_build, Decimal("1.16")),
        (report.cloud_build_build_images, Decimal("1.03")),
        (report.cloud_build_verify_images, Decimal("0.13")),
        (report.logging, Decimal("0.14")),
        (report.monitoring, Decimal("1.42")),
        (report.network_egress, Decimal("0.00")),
        (report.cross_region_data_transfer, Decimal("0.00")),
        (report.total, Decimal("19.50")),
    )
    assert all(actual == expected for actual, expected in expected_components)
    assert report.usd_to_brl == Decimal("5.50")
    assert str(report.usd_to_brl_as_of) == "2026-08-30"
    assert report.rate_basis == "gross_without_free_tier"
    assert report.total == sum(
        (
            report.bigquery,
            report.bigquery_storage_write_api,
            report.bigquery_active_storage,
            report.dataflow,
            report.storage,
            report.pubsub,
            report.cloud_run,
            report.workflows,
            report.scheduler,
            report.artifact_registry,
            report.cloud_build,
            report.logging,
            report.monitoring,
            report.network_egress,
            report.cross_region_data_transfer,
        ),
        start=Decimal("0.00"),
    )


def test_cloud_run_cost_when_failure_handler_is_invoked() -> None:
    catalog = load_catalog(CATALOG)
    success_profile = catalog.profiles["demo"]
    failure_profile = success_profile.model_copy(
        update={
            "cloud_run_vcpu_seconds": success_profile.cloud_run_vcpu_seconds + Decimal(60),
            "cloud_run_gib_seconds": success_profile.cloud_run_gib_seconds + Decimal(120),
        }
    )
    failure_catalog = catalog.model_copy(update={"profiles": {"demo": failure_profile}})

    report = estimate_profile(failure_catalog, "demo")

    assert report.cloud_run == Decimal("0.10")
    assert report.total == Decimal("19.51")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bigquery_max_bytes_billed_per_query", 26 * 1024**3),
        ("dataflow_max_workers", 0),
        ("dataflow_max_workers", 3),
    ],
)
def test_cost_request_when_hard_limit_is_invalid(field: str, value: int) -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data[field] = value

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


def test_cost_request_when_currency_is_not_brl() -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data["currency"] = "USD"

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cloud_run_vcpu_seconds", "-0.01"),
        ("dataflow_runtime_hours", "-0.01"),
        ("pubsub_gcs_export_gib", "-0.01"),
        ("gcs_replication_written_gib", "-0.01"),
        ("workflows_internal_steps", -1),
        ("monitoring_mib", "-0.01"),
        ("network_egress_gib", "-0.01"),
        ("bigquery_storage_write_api_gib", "-0.01"),
    ],
)
def test_cost_request_when_extended_quantity_is_negative(field: str, value: str | int) -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data[field] = value

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "cloud_run_vcpu_seconds",
        "cloud_run_gib_seconds",
        "dataflow_max_workers",
        "dataflow_runtime_hours",
        "dataflow_worker_vcpus",
        "dataflow_worker_memory_gib",
        "dataflow_disk_gib",
        "dataflow_streaming_engine_compute_unit_hours",
        "bigquery_total_bytes_processed",
        "bigquery_query_count",
        "bigquery_max_bytes_billed_per_query",
        "bigquery_storage_write_api_gib",
        "bigquery_active_storage_gib_month",
        "gcs_storage_gib_month",
        "gcs_replication_written_gib",
        "gcs_class_a_operations_per_1000",
        "gcs_class_b_operations_per_1000",
        "workflows_internal_steps",
        "scheduler_jobs_month",
        "artifact_registry_gib_month",
        "cloud_build_build_images_minutes",
        "cloud_build_verify_images_minutes",
        "logging_gib",
        "monitoring_mib",
        "network_egress_gib",
        "cross_region_data_transfer_gib",
        "pubsub_publish_delivery_gib",
        "pubsub_gcs_export_gib",
        "pubsub_retained_gib_month",
    ],
)
def test_cost_request_when_priced_component_is_missing(field: str) -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    del data[field]

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


@pytest.mark.parametrize("field", ["unpriced_service_units", "workflows_external_steps"])
def test_cost_request_when_unknown_component_is_supplied(field: str) -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data[field] = 1

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        (1, Decimal("0.06")),
        (1000, Decimal("0.06")),
        (1001, Decimal("0.11")),
        (5000, Decimal("0.28")),
        (5001, Decimal("0.33")),
    ],
)
def test_workflows_cost_when_internal_steps_cross_a_billing_block(
    steps: int, expected: Decimal
) -> None:
    catalog = load_catalog(CATALOG)
    profile = catalog.profiles["demo"].model_copy(update={"workflows_internal_steps": steps})
    adjusted_catalog = catalog.model_copy(update={"profiles": {"demo": profile}})

    report = estimate_profile(adjusted_catalog, "demo")

    assert report.workflows == expected


def test_cost_cli_when_demo_is_requested_twice() -> None:
    runner = CliRunner()

    first = runner.invoke(app, ["estimate", "--profile", "demo", "--format", "json"])
    second = runner.invoke(app, ["estimate", "--profile", "demo", "--format", "json"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.stdout == second.stdout
    assert '"total":"19.50"' in first.stdout


def test_cost_cli_when_currency_override_is_invalid() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["estimate", "--profile", "demo", "--format", "json", "--currency", "USD"],
    )

    assert result.exit_code == 2


@pytest.mark.parametrize(
    "fixture",
    ["tests/ops/fixtures/invalid_bytes.yml", "tests/ops/fixtures/invalid_workers.yml"],
)
def test_cost_cli_when_profile_breaks_hard_limit(fixture: str) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["estimate", "--profile", "demo", "--format", "json", "--catalog", fixture],
    )

    assert result.exit_code == 2
    response = InvalidCostResponse.model_validate_json(result.stderr)
    assert response.error_code == "invalid_cost_catalog"
    assert response.error_count >= 1
