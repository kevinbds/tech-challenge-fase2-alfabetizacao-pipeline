from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from alfabetizacao_pipeline.ops.costs import app, estimate_profile, load_catalog
from alfabetizacao_pipeline.ops.models import CostRequest, Currency, InvalidCostResponse

CATALOG = Path("ops/cost_profiles.yml")


def test_demo_cost_when_profile_is_estimated() -> None:
    # Given: the versioned demo profile and its explicit price assumptions.
    catalog = load_catalog(CATALOG)

    # When: the deterministic estimator evaluates the profile.
    report = estimate_profile(catalog, "demo")

    # Then: every monetary component and the total are exact BRL amounts.
    assert report.currency is Currency.BRL
    assert report.bigquery == Decimal("0.76")
    assert report.dataflow == Decimal("0.08")
    assert report.storage == Decimal("0.13")
    assert report.pubsub == Decimal("0.00")
    assert report.total == Decimal("0.97")


@pytest.mark.parametrize(
    ("field", "value"),
    [("bytes_processed", 26 * 1024**3), ("workers", 0), ("workers", 3)],
)
def test_cost_request_when_hard_limit_is_invalid(field: str, value: int) -> None:
    # Given: otherwise valid FinOps input with one invalid hard-limit field.
    data = {
        "currency": "BRL",
        "bytes_processed": 1024,
        "workers": 1,
        "worker_hours": "0.25",
        "storage_gb_month": "1",
        "pubsub_gib": "0.01",
    }
    data[field] = value

    # When/Then: boundary parsing rejects the illegal state.
    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


def test_cost_request_when_currency_is_not_brl() -> None:
    # Given: a profile denominated in a currency outside the approved baseline.
    data = {
        "currency": "USD",
        "bytes_processed": 1024,
        "workers": 1,
        "worker_hours": "0.25",
        "storage_gb_month": "1",
        "pubsub_gib": "0.01",
    }

    # When/Then: unsupported currency is rejected at the boundary.
    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


def test_cost_cli_when_demo_is_requested_twice() -> None:
    # Given: two independent invocations through the real CLI surface.
    runner = CliRunner()

    # When: the same profile is estimated twice.
    first = runner.invoke(app, ["estimate", "--profile", "demo", "--format", "json"])
    second = runner.invoke(app, ["estimate", "--profile", "demo", "--format", "json"])

    # Then: JSON and exit status are deterministic.
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.stdout == second.stdout
    assert '"total":"0.97"' in first.stdout


def test_cost_cli_when_currency_override_is_invalid() -> None:
    # Given: the real CLI and an unsupported currency override.
    runner = CliRunner()

    # When: a caller tries to estimate in USD.
    result = runner.invoke(
        app,
        ["estimate", "--profile", "demo", "--format", "json", "--currency", "USD"],
    )

    # Then: Typer returns the stable invalid-input exit code.
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "fixture",
    ["tests/ops/fixtures/invalid_bytes.yml", "tests/ops/fixtures/invalid_workers.yml"],
)
def test_cost_cli_when_profile_breaks_hard_limit(fixture: str) -> None:
    # Given: an invalid versioned profile received through the CLI boundary.
    runner = CliRunner()

    # When: the estimator parses the profile.
    result = runner.invoke(
        app,
        ["estimate", "--profile", "demo", "--format", "json", "--catalog", fixture],
    )

    # Then: invalid bytes/workers produce stable exit code 2 without an estimate.
    assert result.exit_code == 2
    response = InvalidCostResponse.model_validate_json(result.stderr)
    assert response.error_code == "invalid_cost_catalog"
    assert response.error_count == 1
