import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar, Final

import pytest
from pydantic import BaseModel, ConfigDict

SECRET_SCAN_LAUNCHER: Final = ("bash", "scripts/gitleaks-scan.sh")


class WorkflowStep(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    run: str | None = None


class WorkflowJob(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    steps: tuple[WorkflowStep, ...]


class CiWorkflow(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    jobs: dict[str, WorkflowJob]


def secret_scan_command() -> tuple[str, ...]:
    workflow = CiWorkflow.model_validate_json(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    commands = tuple(step.run for step in workflow.jobs["secret_scan"].steps if step.run)
    return tuple(shlex.split(commands[-1]))


def scan_command_for_host(command: tuple[str, ...]) -> tuple[str, ...]:
    if os.name != "nt":
        return command
    git = shutil.which("git")
    assert git is not None
    for parent in Path(git).parents:
        git_bash = parent / "usr" / "bin" / "bash.exe"
        if git_bash.is_file():
            return (str(git_bash), *command[1:])
    pytest.fail("Git Bash executable not found beside Git")


def test_secret_scan_job_when_checkout_is_clean_executes_real_command() -> None:
    # Given: the exact command versioned in the secret_scan CI job.
    command = secret_scan_command()

    # When: the real scanner inspects the current checkout and its last commit.
    completed = subprocess.run(
        scan_command_for_host(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Then: module resolution, CLI invocation and the scan all succeed.
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert command[:2] == SECRET_SCAN_LAUNCHER


def test_secret_scan_when_temp_directory_contains_generated_token_fails_closed(
    tmp_path: Path,
) -> None:
    # Given: a token assembled only at runtime outside the tracked checkout.
    synthetic = "AK" + "IA" + "A1B2C3D4E5F6G7H8"
    fixture = tmp_path / "synthetic.txt"
    _ = fixture.write_text(f"token={synthetic}\n", encoding="utf-8")
    command = (*secret_scan_command()[:2], "dir", "--no-banner", "--redact", str(tmp_path))

    # When: the same pinned scanner inspects the temporary directory.
    completed = subprocess.run(
        scan_command_for_host(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Then: the synthetic leak is rejected without echoing its value.
    assert completed.returncode == 1
    assert synthetic not in completed.stdout + completed.stderr
