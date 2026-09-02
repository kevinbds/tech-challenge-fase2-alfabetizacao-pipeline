import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from alfabetizacao_pipeline.streaming.avro_types import ReleaseContext
from alfabetizacao_pipeline.streaming.demo import app, run_demo


def test_demo_produces_exact_e2e_counts_and_is_idempotent(tmp_path: Path) -> None:
    fixture = Path("contracts/events/fixtures/demo.json")
    release = ReleaseContext(
        target_year=2024,
        base_time=datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC),
        correlation_id="local-2024",
    )

    first = run_demo(fixture, tmp_path, release)
    second = run_demo(fixture, tmp_path, release)

    assert first == second
    assert first.raw_message_ids == 10
    assert first.valid_event_ids == 8
    assert first.duplicate_audit == 1
    assert first.quarantine == 1
    assert first.schema_rejected == 1
    assert first.redeliveries_tolerated == 1
    assert first.p95_latency_seconds < 60
    valid_lines = (tmp_path / "valid.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(valid_lines) == 8
    assert len({json.loads(line)["event_id"] for line in valid_lines}) == 8
    assert {json.loads(line)["ano"] for line in valid_lines} == {2024}
    assert {json.loads(line)["rede"] for line in valid_lines} == {"publica"}


def test_demo_cli_rejects_invalid_format_before_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "demo-output"

    result = CliRunner().invoke(
        app,
        [
            "--fixture",
            "contracts/events/fixtures/demo.json",
            "--output",
            str(output),
            "--year",
            "2031",
            "--format",
            "csv",
        ],
    )

    assert result.exit_code == 2
    assert not output.exists()
