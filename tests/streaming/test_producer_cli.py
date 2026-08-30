import os
import re
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


def test_workflow_fixture_when_image_is_built_uses_copied_destination(tmp_path: Path) -> None:
    # Given: the fixture source and destination declared by the producer image.
    dockerfile = Path("containers/producer.Dockerfile").read_text(encoding="utf-8")
    source_pattern = r"^COPY --chown=[^ ]+ (?P<source>contracts/events/fixtures/demo\.json)"
    destination_pattern = r"(?P<destination>/[^\r\n ]+)$"
    copy_pattern = f"{source_pattern} {destination_pattern}"
    copied_fixture = re.search(
        copy_pattern,
        dockerfile,
        flags=re.MULTILINE,
    )
    assert copied_fixture is not None
    source = copied_fixture.group("source")
    destination = copied_fixture.group("destination")
    workflow = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")
    workflow_fixture = re.search(r"--fixture,\s*(?P<fixture>/[^,\]\s]+)", workflow)
    assert workflow_fixture is not None
    report = tmp_path / "producer-runtime-report.json"

    # When: the copied source is exercised through the producer's real CLI.
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
            source,
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: the image fixture is valid and the Workflow addresses that exact destination.
    assert completed.returncode == 0, completed.stderr
    assert report.read_text(encoding="utf-8") == (
        '{"mode": "local", "published": 10, "schema_rejected": 1}\n'
    )
    assert workflow_fixture.group("fixture") == destination


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
