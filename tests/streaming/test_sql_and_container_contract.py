import re
from pathlib import Path


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
