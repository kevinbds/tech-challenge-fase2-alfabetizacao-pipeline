import os
import subprocess

from alfabetizacao_pipeline.cli import app


def test_help_when_cli_is_installed() -> None:
    # Given: the executable is expected to be available in the active environment.
    command = ["alfabetizacao", "--help"]

    # When: a user opens the command help.
    completed = subprocess.run(command, capture_output=True, check=False, text=True)

    # Then: the CLI advertises itself successfully.
    assert completed.returncode == 0


def test_help_is_plain_when_output_is_captured() -> None:
    # Given: a color-capable output capture like an automation wrapper.
    environment = os.environ.copy()
    environment["FORCE_COLOR"] = "1"

    # When: the wrapper captures the root help.
    completed = subprocess.run(
        ["alfabetizacao", "--help"],
        capture_output=True,
        check=False,
        env=environment,
        timeout=10,
    )

    # Then: help remains portable plain text without terminal control codes.
    assert completed.returncode == 0
    assert b"\x1b" not in completed.stdout
    assert app.rich_markup_mode is None
