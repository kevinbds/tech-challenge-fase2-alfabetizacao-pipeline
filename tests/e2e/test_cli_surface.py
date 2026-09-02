import os
import subprocess

from alfabetizacao_pipeline.cli import app


def test_help_when_cli_is_installed() -> None:
    command = ["alfabetizacao", "--help"]

    completed = subprocess.run(command, capture_output=True, check=False, text=True)

    assert completed.returncode == 0


def test_help_is_plain_when_output_is_captured() -> None:
    environment = os.environ.copy()
    environment["FORCE_COLOR"] = "1"

    completed = subprocess.run(
        ["alfabetizacao", "--help"],
        capture_output=True,
        check=False,
        env=environment,
        timeout=10,
    )

    assert completed.returncode == 0
    assert b"\x1b" not in completed.stdout
    assert app.rich_markup_mode is None
