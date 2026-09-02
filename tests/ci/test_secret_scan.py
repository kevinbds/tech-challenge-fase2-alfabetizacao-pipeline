import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar, Final

import pytest
from pydantic import BaseModel, ConfigDict, Field

SECRET_SCAN_LAUNCHER: Final = ("bash", "scripts/gitleaks-scan.sh")
RANGE_SCAN_LAUNCHER: Final = ("bash", "scripts/gitleaks-scan-range.sh")


class WorkflowStep(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    run: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class WorkflowJob(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    steps: tuple[WorkflowStep, ...]


class CiWorkflow(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    jobs: dict[str, WorkflowJob]


def range_scan_command() -> tuple[str, ...]:
    return (
        "bash",
        str(Path("scripts/gitleaks-scan-range.sh").resolve()),
    )


def git_commit(repository: Path, message: str) -> str:
    completed = subprocess.run(
        ("git", "commit", "--allow-empty", "-m", message),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def run_range_scan(
    repository: Path,
    *,
    event_name: str,
    head_sha: str,
    push_before: str = "",
    pr_base_sha: str = "",
) -> tuple[str, ...]:
    environment = os.environ | {
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_SHA": head_sha,
        "GITLEAKS_PUSH_BEFORE": push_before,
        "GITLEAKS_PR_BASE_SHA": pr_base_sha,
        "GITLEAKS_SCANNER": "/usr/bin/echo",
    }
    completed = subprocess.run(
        scan_command_for_host(range_scan_command()),
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return tuple(shlex.split(completed.stdout))


def initialize_repository(repository: Path) -> None:
    completed = subprocess.run(
        ("git", "init", "--quiet", repository),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    for setting in ("user.email=test@example.com", "user.name=Test User"):
        completed = subprocess.run(
            ("git", "-C", repository, "config", *setting.split("=", maxsplit=1)),
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


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
        git_bash = parent / "bin" / "bash.exe"
        if git_bash.is_file():
            return (str(git_bash), *command[1:])
    pytest.fail("Git Bash executable not found beside Git")


def test_secret_scan_job_when_checkout_is_clean_executes_real_command() -> None:
    command = secret_scan_command()

    completed = subprocess.run(
        scan_command_for_host(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert command[:2] == RANGE_SCAN_LAUNCHER


def test_secret_scan_workflow_when_event_metadata_is_available_provides_both_ranges() -> None:
    workflow = CiWorkflow.model_validate_json(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    range_step = next(
        step
        for step in workflow.jobs["secret_scan"].steps
        if step.run == "bash scripts/gitleaks-scan-range.sh"
    )

    assert range_step.env == {
        "GITLEAKS_PUSH_BEFORE": "${{ github.event.before }}",
        "GITLEAKS_PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
    }


def test_secret_scan_when_temp_directory_contains_generated_token_fails_closed(
    tmp_path: Path,
) -> None:
    synthetic = "AK" + "IA" + "A1B2C3D4E5F6G7H8"
    fixture = tmp_path / "synthetic.txt"
    _ = fixture.write_text(f"token={synthetic}\n", encoding="utf-8")
    command = (*SECRET_SCAN_LAUNCHER, "dir", "--no-banner", "--redact", str(tmp_path))

    completed = subprocess.run(
        scan_command_for_host(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 1
    assert synthetic not in completed.stdout + completed.stderr


def test_range_scan_when_push_has_valid_before_covers_every_new_commit(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    initialize_repository(repository)
    before = git_commit(repository, "base")
    _ = git_commit(repository, "intermediate")
    head = git_commit(repository, "head")

    arguments = run_range_scan(
        repository,
        event_name="push",
        head_sha=head,
        push_before=before,
    )

    assert arguments[-1] == f"--log-opts={before}..{head}"
    commits = subprocess.run(
        ("git", "-C", repository, "rev-list", f"{before}..{head}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert len(commits) == 2


def test_range_scan_when_pull_request_has_base_uses_base_to_head(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    initialize_repository(repository)
    base = git_commit(repository, "base")
    head = git_commit(repository, "pull request change")

    arguments = run_range_scan(
        repository,
        event_name="pull_request",
        head_sha=head,
        pr_base_sha=base,
    )

    assert arguments[-1] == f"--log-opts={base}..{head}"


@pytest.mark.parametrize("before", ["0" * 40, "a" * 40])
def test_range_scan_when_push_before_is_unavailable_scans_reachable_history(
    tmp_path: Path,
    before: str,
) -> None:
    repository = tmp_path / "repository"
    initialize_repository(repository)
    _ = git_commit(repository, "first commit")
    head = git_commit(repository, "second commit")

    arguments = run_range_scan(
        repository,
        event_name="push",
        head_sha=head,
        push_before=before,
    )

    assert arguments[-1] == "--log-opts=HEAD"
