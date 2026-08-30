import os
import subprocess
import sys
from pathlib import Path


def test_producer_has_standalone_help_surface() -> None:
    # Given the standalone producer module
    # When its real CLI help is invoked
    completed = subprocess.run(
        [sys.executable, "-m", "alfabetizacao_pipeline.streaming.producer", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the cloud/local mode boundary is explicit
    assert completed.returncode == 0
    assert "--mode" in completed.stdout
    assert "--topic" in completed.stdout


def test_local_producer_publishes_ten_and_rejects_incompatible_before_port(tmp_path: Path) -> None:
    # Given the deterministic fixture and an explicitly selected local mode
    report = tmp_path / "producer-report.json"

    # When the standalone producer executes through its real CLI
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "alfabetizacao_pipeline.streaming.producer",
            "--mode",
            "local",
            "--topic",
            "projects/demo/topics/literacy",
            "--fixture",
            "contracts/events/fixtures/demo.json",
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then only the ten Avro-compatible records reach the publisher
    assert completed.returncode == 0, completed.stderr
    assert report.read_text(encoding="utf-8") == (
        '{"mode": "local", "published": 10, "schema_rejected": 1}\n'
    )


def test_local_producer_uses_cloud_run_environment_when_options_are_omitted(
    tmp_path: Path,
) -> None:
    # Given the environment injected by the Terraform Cloud Run job and Workflow override
    report = tmp_path / "producer-report.json"
    environment = os.environ.copy()
    environment["PUBSUB_TOPIC"] = "projects/demo/topics/literacy"
    environment["CORRELATION_ID"] = "integration-run"

    # When the standalone producer runs without topic or correlation CLI options
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "alfabetizacao_pipeline.streaming.producer",
            "--mode",
            "local",
            "--fixture",
            "contracts/events/fixtures/demo.json",
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    # Then the runtime boundary supplies every omitted required value
    assert completed.returncode == 0, completed.stderr
    assert report.is_file()
