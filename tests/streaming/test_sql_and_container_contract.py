import re
import subprocess
import sys
from pathlib import Path

from pydantic import TypeAdapter

from alfabetizacao_pipeline.streaming.beam_routes import QuarantineRow, StagedEventRow

VALID_ROW_ADAPTER = TypeAdapter(StagedEventRow)
QUARANTINE_ROW_ADAPTER = TypeAdapter(QuarantineRow)


def test_stream_sql_encodes_deterministic_source_and_overlay_ordering() -> None:
    # Given the versioned streaming SQL artifacts
    source = Path("sql/streaming/dedupe_source.sql").read_text(encoding="utf-8")
    audit = Path("sql/streaming/audit_duplicates.sql").read_text(encoding="utf-8")
    merge = Path("sql/streaming/merge_current.sql").read_text(encoding="utf-8")

    # When their executable contracts are inspected
    normalized_source = " ".join(source.split()).lower()
    normalized_audit = " ".join(audit.split()).lower()
    normalized_merge = " ".join(merge.split()).lower()

    # Then source and overlay tie-breaks are deterministic and simulation-only
    assert "qualify row_number() over" in normalized_source
    assert "order by event_time desc, publish_time desc, ingestion_time desc" in normalized_source
    assert "order by event_time desc, publish_time desc, ingestion_time desc" in normalized_audit
    assert ") > 1" in normalized_audit
    assert "message_id" in normalized_audit
    assert "order by event_time desc, publish_time desc, event_id desc" in normalized_merge
    assert "simulation = true" in normalized_merge


def test_dataflow_container_is_pinned_and_portable() -> None:
    # Given the custom Dataflow image definition
    dockerfile = Path("containers/dataflow.Dockerfile").read_text(encoding="utf-8")

    # When its runtime contract is inspected
    # Then it never uses latest and opts into the portable runner
    assert "@sha256:" in dockerfile.partition("\n")[0]
    assert "enable_portable_runner" in dockerfile
    assert ":latest" not in dockerfile


def test_dataflow_container_references_only_materialized_build_context_paths() -> None:
    # Given every COPY and Flex file variable in the Dockerfile
    dockerfile = Path("containers/dataflow.Dockerfile").read_text(encoding="utf-8")
    copy_sources = [
        match.group(1) for match in re.finditer(r"^COPY ([^ ]+)", dockerfile, flags=re.MULTILINE)
    ]
    flex_files = [
        match.group(1)
        for match in re.finditer(
            r"FLEX_TEMPLATE_PYTHON_[A-Z_]+=/opt/pipeline/([^ \\\n]+)", dockerfile
        )
    ]

    # When the repository root is treated as the build context
    missing_copy = [source for source in copy_sources if not Path(source).exists()]
    missing_flex = [name for name in flex_files if not Path("containers/dataflow", name).exists()]

    # Then Docker and the official Flex launcher can resolve every artifact
    assert missing_copy == []
    assert missing_flex == []
    assert Path("containers/dataflow/beam_entrypoint.py").is_file()
    assert Path("containers/dataflow/requirements-dataflow.txt").is_file()


def test_dataflow_entrypoint_when_fixture_runs_matches_bigquery_rows(tmp_path: Path) -> None:
    # Given: the real Flex Python entrypoint and the ten schema-compatible events.
    output_dir = tmp_path / "beam"
    output_dir.mkdir()

    # When: the same argparse boundary used by Dataflow runs through DirectRunner.
    completed = subprocess.run(
        [
            sys.executable,
            "containers/dataflow/beam_entrypoint.py",
            "--fixture",
            "contracts/events/fixtures/demo.json",
            "--output_dir",
            str(output_dir),
            "--valid_table",
            "project:silver.municipal_rate_stream",
            "--quarantine_table",
            "project:quarantine.stream_events",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Then: staging and quarantine rows match the physical BigQuery contracts.
    assert completed.returncode == 0, completed.stdout + completed.stderr
    valid = [
        VALID_ROW_ADAPTER.validate_json(line)
        for path in output_dir.glob("valid-*")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    quarantine = [
        QUARANTINE_ROW_ADAPTER.validate_json(line)
        for path in output_dir.glob("quarantine-*")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(valid) == 9
    assert len({row["event_id"] for row in valid}) == 8
    assert len(quarantine) == 1
    assert set(valid[0]) == {
        "event_id",
        "message_id",
        "event_time",
        "publish_time",
        "ingestion_time",
        "ano",
        "id_municipio",
        "rede",
        "taxa_alfabetizacao",
        "taxa_participacao",
        "correlation_id",
        "simulation",
    }
    assert set(quarantine[0]) == {"message_id", "ingestion_time", "reason_code"}
