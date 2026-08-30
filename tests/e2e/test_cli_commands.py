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
    # Given: the package console script is installed.
    arguments = ["version"]

    # When: a user requests the application version.
    completed = run_cli(arguments)

    # Then: the version command succeeds with the package version.
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"


def test_json_when_configuration_is_valid() -> None:
    # Given: the default local configuration is valid.
    arguments = ["config", "check", "--format", "json"]

    # When: automation validates the configuration.
    completed = run_cli(arguments)

    # Then: stdout contains a successful machine-readable result.
    payload = ConfigCheck.model_validate_json(completed.stdout)
    assert completed.returncode == 0
    assert payload.status == "ok"
    assert "secret" not in completed.stdout.lower()


def test_exit_two_when_configuration_is_invalid() -> None:
    # Given: a copied environment with an invalid query cap.
    environment = os.environ.copy()
    environment["ALFABETIZACAO_MAX_BYTES_BILLED"] = "0"

    # When: automation validates the configuration.
    completed = run_cli(["config", "check", "--format", "json"], environment)

    # Then: the CLI reports only a redacted summary and exits with code two.
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
    # Given: a copied environment with one malformed GCP identifier.
    environment = os.environ.copy()
    environment[environment_name] = invalid_value

    # When: automation validates the configuration boundary.
    completed = run_cli(["config", "check", "--format", "json"], environment)

    # Then: the CLI emits only the redacted JSON summary and exits with code two.
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
    # Given: the current Python interpreter and installed package.
    arguments = ["-m", "alfabetizacao_pipeline", "version"]

    # When: Python invokes the package module entrypoint.
    completed = subprocess.run(
        [sys.executable, *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )

    # Then: the module dispatches to the same CLI.
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"
