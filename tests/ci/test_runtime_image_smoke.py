import os
import subprocess
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict

BASH_PATH: Final = os.environ.get(
    "GIT_BASH_PATH",
    r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash",
)
TEST_GIT_SHA: Final = "a" * 40


class SmokeCheck(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    name: str
    arguments: tuple[str, ...]
    expected_exit: int
    docker_entrypoint: str | None = None


class SmokeImage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    entrypoint: tuple[str, ...]
    checks: tuple[SmokeCheck, ...]


class SmokeContract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    digest_required: bool
    timeout_seconds: int
    images: dict[str, SmokeImage]


class SmokeCheckReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: str
    exit_code: int


class SmokeImageReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    reference: str
    status: str
    checks: tuple[SmokeCheckReport, ...]


class SmokeReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    contract_version: str
    git_sha: str
    approval_mode: bool
    overall: str
    images: dict[str, SmokeImageReport]


def test_smoke_contract_requires_digest_and_separates_container_arguments() -> None:
    contract = SmokeContract.model_validate_json(
        Path("containers/smoke-contract.json").read_text(encoding="utf-8")
    )

    assert contract.version == "2.0"
    assert contract.digest_required is True
    assert contract.images["batch"].entrypoint == ("alfabetizacao", "batch", "run")
    assert contract.images["dataflow_template"].entrypoint == (
        "/opt/google/dataflow/python_template_launcher",
    )
    assert contract.images["dataflow_sdk"].entrypoint == ("/opt/apache/beam/boot",)


def test_smoke_rejects_mutable_tag_before_running_docker(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker-fake"
    _ = fake_docker.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    _ = fake_docker.chmod(0o755)

    result = subprocess.run(
        (
            BASH_PATH,
            "scripts/verify-runtime-images.sh",
            "--git-sha",
            TEST_GIT_SHA,
            "--docker",
            str(fake_docker),
            "--batch",
            "registry.example/batch:local",
            "--dbt",
            "registry.example/dbt@sha256:" + "a" * 64,
            "--producer",
            "registry.example/producer@sha256:" + "b" * 64,
            "--dataflow-template",
            "registry.example/dataflow-template@sha256:" + "c" * 64,
            "--dataflow-sdk",
            "registry.example/dataflow-sdk@sha256:" + "d" * 64,
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "immutable digest" in result.stderr


def test_smoke_writes_machine_report_from_fake_docker(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker-fake"
    calls = tmp_path / "docker-calls.log"
    report = tmp_path / "runtime-smoke.json"
    _ = fake_docker.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$DOCKER_CALLS"
if [[ $1 == inspect ]]; then
  case "$*" in
    *dataflow-template*) printf '%s\\n' '["/opt/google/dataflow/python_template_launcher"]' ;;
    *dataflow-sdk*) printf '%s\\n' '["/opt/apache/beam/boot"]' ;;
  esac
fi
exit "${DOCKER_EXIT_CODE:-0}"
""",
        encoding="utf-8",
    )
    _ = fake_docker.chmod(0o755)
    local_tags = (
        "fiap-audit-batch:local",
        "fiap-audit-dbt:local",
        "fiap-audit-producer:local",
        "fiap-audit-dataflow-template:local",
        "fiap-audit-dataflow-sdk:local",
    )

    result = subprocess.run(
        (
            BASH_PATH,
            "scripts/verify-runtime-images.sh",
            "--git-sha",
            TEST_GIT_SHA,
            "--docker",
            str(fake_docker),
            "--allow-local-tags",
            "--report",
            str(report),
            "--batch",
            local_tags[0],
            "--dbt",
            local_tags[1],
            "--producer",
            local_tags[2],
            "--dataflow-template",
            local_tags[3],
            "--dataflow-sdk",
            local_tags[4],
        ),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_CALLS": str(calls)},
    )

    assert result.returncode == 0, result.stderr
    payload = SmokeReport.model_validate_json(report.read_text(encoding="utf-8"))
    assert payload.overall == "passed"
    assert payload.git_sha
    assert set(payload.images) == {
        "batch",
        "dbt",
        "producer",
        "dataflow_template",
        "dataflow_sdk",
    }
    assert payload.images["dataflow_template"].status == "passed"
    assert payload.images["dataflow_sdk"].status == "passed"
    assert all(image.status == "passed" for image in payload.images.values()), payload
    assert "run --rm fiap-audit-batch:local --help" in calls.read_text(encoding="utf-8")


def test_smoke_accepts_immutable_references_in_approval_mode(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker-fake"
    report = tmp_path / "runtime-smoke.json"
    _ = fake_docker.write_text(
        """#!/usr/bin/env bash
if [[ $1 == inspect ]]; then
  case "$*" in
    *dataflow-template*) printf '%s\\n' '["/opt/google/dataflow/python_template_launcher"]' ;;
    *dataflow-sdk*) printf '%s\\n' '["/opt/apache/beam/boot"]' ;;
  esac
fi
exit 0
""",
        encoding="utf-8",
    )
    _ = fake_docker.chmod(0o755)

    result = subprocess.run(
        (
            BASH_PATH,
            "scripts/verify-runtime-images.sh",
            "--git-sha",
            TEST_GIT_SHA,
            "--docker",
            str(fake_docker),
            "--report",
            str(report),
            "--batch",
            "registry.example/batch@sha256:" + "a" * 64,
            "--dbt",
            "registry.example/dbt@sha256:" + "b" * 64,
            "--producer",
            "registry.example/producer@sha256:" + "c" * 64,
            "--dataflow-template",
            "registry.example/dataflow-template@sha256:" + "d" * 64,
            "--dataflow-sdk",
            "registry.example/dataflow-sdk@sha256:" + "e" * 64,
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = SmokeReport.model_validate_json(report.read_text(encoding="utf-8"))
    assert payload.approval_mode is True
    assert payload.overall == "passed"


def test_smoke_marks_nonzero_container_check_as_failed(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker-fake"
    report = tmp_path / "runtime-smoke.json"
    _ = fake_docker.write_text(
        '#!/usr/bin/env bash\nexit "${DOCKER_EXIT_CODE:-0}"\n', encoding="utf-8"
    )
    _ = fake_docker.chmod(0o755)

    result = subprocess.run(
        (
            BASH_PATH,
            "scripts/verify-runtime-images.sh",
            "--git-sha",
            TEST_GIT_SHA,
            "--docker",
            str(fake_docker),
            "--allow-local-tags",
            "--report",
            str(report),
            "--batch",
            "fiap-audit-batch:local",
            "--dbt",
            "fiap-audit-dbt:local",
            "--producer",
            "fiap-audit-producer:local",
            "--dataflow-template",
            "fiap-audit-dataflow-template:local",
            "--dataflow-sdk",
            "fiap-audit-dataflow-sdk:local",
        ),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_EXIT_CODE": "7"},
    )

    assert result.returncode == 1
    assert SmokeReport.model_validate_json(report.read_text(encoding="utf-8")).overall == "failed"
