import os
import subprocess
import sys
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from alfabetizacao_pipeline.config import ConfigCheck


class InvalidConfigResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: str
    error_count: int


def run_cli(
    arguments: list[str],
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alfabetizacao", *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
        timeout=10,
    )


def test_version_when_cli_is_installed() -> None:
    arguments = ["version"]

    completed = run_cli(arguments)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"


def test_json_when_configuration_is_valid() -> None:
    arguments = ["config", "check", "--format", "json"]

    completed = run_cli(arguments)

    payload = ConfigCheck.model_validate_json(completed.stdout)
    assert completed.returncode == 0
    assert payload.status == "ok"
    assert "secret" not in completed.stdout.lower()


def test_exit_two_when_configuration_is_invalid() -> None:
    environment = os.environ.copy()
    environment["ALFABETIZACAO_MAX_BYTES_BILLED"] = "0"

    completed = run_cli(["config", "check", "--format", "json"], environment)

    payload = InvalidConfigResult.model_validate_json(completed.stderr)
    assert completed.returncode == 2
    assert payload.status == "invalid"
    assert payload.error_count == 1
    assert "secret" not in completed.stderr.lower()


@pytest.mark.parametrize(
    ("environment_name", "invalid_value"),
    [
        ("ALFABETIZACAO_GCP_PROJECT_ID", "INVALID PROJECT!"),
        ("ALFABETIZACAO_GCP_REGION", "not a region!"),
    ],
)
def test_exit_two_when_gcp_identifier_is_invalid(
    environment_name: str,
    invalid_value: str,
) -> None:
    environment = os.environ.copy()
    environment[environment_name] = invalid_value

    completed = run_cli(["config", "check", "--format", "json"], environment)

    payload = InvalidConfigResult.model_validate_json(completed.stderr)
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert payload.status == "invalid"
    assert payload.error_count == 1
    assert invalid_value not in completed.stderr
    assert all(
        sensitive not in completed.stderr.lower()
        for sensitive in ("secret", "token", "password", "credential")
    )


def test_module_entrypoint_when_invoked() -> None:
    arguments = ["-m", "alfabetizacao_pipeline", "version"]

    completed = subprocess.run(
        [sys.executable, *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"
