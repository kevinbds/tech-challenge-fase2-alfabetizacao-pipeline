from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.config import AppSettings


def test_defaults_when_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: no configuration override is present.
    monkeypatch.delenv("ALFABETIZACAO_MAX_BYTES_BILLED", raising=False)
    monkeypatch.chdir(tmp_path)

    # When: settings are parsed at the environment boundary.
    settings = AppSettings()

    # Then: safe local and cost defaults are available.
    assert settings.gcp_project_id == "local-project"
    assert settings.max_bytes_billed == 25 * 1024**3
    assert settings.budget_amount == Decimal(50)


def test_validation_error_when_cost_limit_is_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the configured query cap is invalid.
    monkeypatch.setenv("ALFABETIZACAO_MAX_BYTES_BILLED", "0")
    monkeypatch.chdir(tmp_path)

    # When: settings parse the invalid boundary value.
    with pytest.raises(ValidationError) as captured:
        _ = AppSettings()

    # Then: validation identifies the cost-limit field.
    assert captured.value.error_count() == 1
    assert captured.value.errors()[0]["loc"] == ("max_bytes_billed",)


def test_settings_are_frozen_when_created(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: a valid settings object.
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()

    # When: a caller attempts to mutate it.
    with pytest.raises(ValidationError) as captured:
        settings.gcp_region = "us-central1"

    # Then: Pydantic rejects the mutation.
    assert captured.value.errors()[0]["type"] == "frozen_instance"


def test_branded_values_when_settings_are_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: settings parsed without a local environment file.
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()

    # When: domain-specific projections are requested.
    project_id = settings.project_id
    bytes_billed_limit = settings.bytes_billed_limit

    # Then: projections preserve their validated primitive values.
    assert project_id == "local-project"
    assert bytes_billed_limit == 25 * 1024**3
