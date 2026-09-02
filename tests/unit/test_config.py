from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.config import AppSettings


def test_defaults_when_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ALFABETIZACAO_MAX_BYTES_BILLED", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()
    assert settings.gcp_project_id == "local-project"
    assert settings.gcp_region == "us-central1"
    assert settings.max_bytes_billed == 25 * 1024**3
    assert settings.budget_amount == Decimal(50)


def test_validation_error_when_cost_limit_is_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ALFABETIZACAO_MAX_BYTES_BILLED", "0")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as captured:
        _ = AppSettings()
    assert captured.value.error_count() == 1
    assert captured.value.errors()[0]["loc"] == ("max_bytes_billed",)


def test_settings_are_frozen_when_created(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()
    with pytest.raises(ValidationError) as captured:
        settings.gcp_region = "us-central1"
    assert captured.value.errors()[0]["type"] == "frozen_instance"


def test_branded_values_when_settings_are_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()
    project_id = settings.project_id
    bytes_billed_limit = settings.bytes_billed_limit
    assert project_id == "local-project"
    assert bytes_billed_limit == 25 * 1024**3


@pytest.mark.parametrize(
    "project_id",
    ["abcde1", "my-project-123", "a" * 30],
)
def test_project_id_when_gcp_contract_is_valid(
    project_id: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ALFABETIZACAO_GCP_PROJECT_ID", project_id)
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()
    assert settings.gcp_project_id == project_id


@pytest.mark.parametrize(
    "project_id",
    ["abcde", "a" * 31, "1abcde", "abcde-", "ABCDEF", "abc_de"],
)
def test_project_id_when_gcp_contract_is_invalid(
    project_id: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ALFABETIZACAO_GCP_PROJECT_ID", project_id)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as captured:
        _ = AppSettings()
    assert captured.value.errors()[0]["loc"] == ("gcp_project_id",)


@pytest.mark.parametrize(
    "region",
    ["southamerica-east1", "us-central1", "northamerica-northeast2"],
)
def test_region_when_gcp_format_is_valid(
    region: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ALFABETIZACAO_GCP_REGION", region)
    monkeypatch.chdir(tmp_path)
    settings = AppSettings()
    assert settings.gcp_region == region


@pytest.mark.parametrize(
    "region",
    ["not a region!", "us-central", "us-central0", "us_central1", "US-central1", "central1"],
)
def test_region_when_gcp_format_is_invalid(
    region: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ALFABETIZACAO_GCP_REGION", region)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as captured:
        _ = AppSettings()
    assert captured.value.errors()[0]["loc"] == ("gcp_region",)
