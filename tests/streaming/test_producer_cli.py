import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from alfabetizacao_pipeline.streaming.producer import ProducerReport

PRODUCER_REPORT: TypeAdapter[ProducerReport] = TypeAdapter(ProducerReport)


def test_producer_has_standalone_help_surface() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alfabetizacao_pipeline.streaming.producer", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    help_text = re.sub(r"\x1b\[[0-9;]*m", "", completed.stdout)
    assert "--mode" in help_text
    assert "--topic" in help_text


def test_local_producer_publishes_ten_and_rejects_incompatible_before_port(tmp_path: Path) -> None:
    report = tmp_path / "producer-report.json"

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
            "--year",
            "2031",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report_data = PRODUCER_REPORT.validate_json(report.read_text(encoding="utf-8"))
    assert report_data.mode == "local"
    assert report_data.published == 10
    assert report_data.schema_rejected == 1
    assert report_data.target_year == 2031
    assert datetime.fromisoformat(report_data.base_time).tzinfo == UTC


def test_workflow_fixture_when_image_is_built_uses_copied_destination(tmp_path: Path) -> None:
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
            "--year",
            "2031",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report_data = PRODUCER_REPORT.validate_json(report.read_text(encoding="utf-8"))
    assert report_data.published == 10
    assert report_data.schema_rejected == 1
    assert report_data.target_year == 2031
    assert workflow_fixture.group("fixture") == destination


def test_local_producer_uses_cloud_run_environment_when_options_are_omitted(
    tmp_path: Path,
) -> None:
    report = tmp_path / "producer-report.json"
    environment = os.environ.copy()
    environment["PUBSUB_TOPIC"] = "projects/demo/topics/literacy"
    environment["CORRELATION_ID"] = "integration-run"

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
            "--year",
            "2031",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert report.is_file()
