from pathlib import Path


def test_stream_sql_encodes_deterministic_source_and_overlay_ordering() -> None:
    # Given the versioned streaming SQL artifacts
    source = Path("sql/streaming/dedupe_source.sql").read_text(encoding="utf-8")
    merge = Path("sql/streaming/merge_current.sql").read_text(encoding="utf-8")

    # When their executable contracts are inspected
    normalized_source = " ".join(source.split()).lower()
    normalized_merge = " ".join(merge.split()).lower()

    # Then source and overlay tie-breaks are deterministic and simulation-only
    assert "qualify row_number() over" in normalized_source
    assert "order by event_time desc, publish_time desc, ingestion_time desc" in normalized_source
    assert "order by event_time desc, publish_time desc, event_id desc" in normalized_merge
    assert "simulation = true" in normalized_merge


def test_dataflow_container_is_pinned_and_portable() -> None:
    # Given the custom Dataflow image definition
    dockerfile = Path("containers/dataflow.Dockerfile").read_text(encoding="utf-8")

    # When its runtime contract is inspected
    # Then it never uses latest and opts into the portable runner
    assert "2.75.0" in dockerfile
    assert "enable_portable_runner" in dockerfile
    assert ":latest" not in dockerfile
