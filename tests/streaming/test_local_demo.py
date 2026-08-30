import json
from pathlib import Path

from alfabetizacao_pipeline.streaming.demo import run_demo


def test_demo_produces_exact_e2e_counts_and_is_idempotent(tmp_path: Path) -> None:
    # Given the deterministic fixture and a local output directory
    fixture = Path("contracts/events/fixtures/demo.json")

    # When the real local pipeline is run twice
    first = run_demo(fixture, tmp_path)
    second = run_demo(fixture, tmp_path)

    # Then the observable contract is exact and the rerun is idempotent
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
