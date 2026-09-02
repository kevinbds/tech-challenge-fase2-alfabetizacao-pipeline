import re
import subprocess
import sys
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from alfabetizacao_pipeline.streaming.beam_routes import QuarantineRow, StagedEventRow

VALID_ROW_ADAPTER = TypeAdapter(StagedEventRow)
QUARANTINE_ROW_ADAPTER = TypeAdapter(QuarantineRow)
JSON_MAPPING = TypeAdapter(dict[str, JsonValue])
JSON_MAPPINGS = TypeAdapter(list[dict[str, JsonValue]])


def test_stream_sql_encodes_deterministic_source_and_overlay_ordering() -> None:
    source = Path("sql/streaming/dedupe_source.sql").read_text(encoding="utf-8")
    audit = Path("sql/streaming/audit_duplicates.sql").read_text(encoding="utf-8")
    merge = Path("sql/streaming/merge_current.sql").read_text(encoding="utf-8")

    normalized_source = " ".join(source.split()).lower()
    normalized_audit = " ".join(audit.split()).lower()
    normalized_merge = " ".join(merge.split()).lower()

    assert "qualify row_number() over" in normalized_source
    assert "order by event_time desc, publish_time desc, ingestion_time desc" in normalized_source
    assert "order by event_time desc, publish_time desc, ingestion_time desc" in normalized_audit
    assert ") > 1" in normalized_audit
    assert "message_id" in normalized_audit
    assert "order by event_time desc, publish_time desc, event_id desc" in normalized_merge
    assert "simulation = true" in normalized_merge


def test_dataflow_container_is_pinned_and_portable() -> None:
    dockerfile = Path("containers/dataflow.Dockerfile").read_text(encoding="utf-8")

    requirements = Path("containers/dataflow/requirements-dataflow.txt").read_text(encoding="utf-8")
    overrides = Path("containers/dataflow/requirements-overrides.txt").read_text(encoding="utf-8")

    assert "@sha256:" in dockerfile.partition("\n")[0]
    assert "python313-template-launcher-base" in dockerfile.partition("\n")[0]
    assert "FLEX_TEMPLATE_PYTHON_PY_FILE=/opt/pipeline/beam_entrypoint.py" in dockerfile
    assert "FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE" not in dockerfile
    assert "enable_portable_runner" in dockerfile
    assert "COPY src/alfabetizacao_pipeline ./alfabetizacao_pipeline" in dockerfile
    assert "apache-beam[gcp]==2.75.0" in requirements
    assert overrides.splitlines() == [
        "aiohttp==3.14.3",
        "cryptography==50.0.1",
        "h2==4.4.1",
        "hpack==4.2.0",
        "httplib2==0.32.0",
        "Pillow==12.3.0",
        "pip==26.2.1",
        "pyasn1==0.6.4",
        "pyOpenSSL==26.4.0",
        "setuptools==84.0.0",
        "sqlparse==0.6.0",
    ]
    assert "--no-deps -r requirements-overrides.txt" in dockerfile
    assert "pip uninstall --yes nltk" in dockerfile
    assert "FROM runtime AS dataflow-dependency-audit" in dockerfile
    assert "FROM runtime AS dataflow-template" in dockerfile
    assert "FROM runtime AS dataflow-sdk" in dockerfile
    assert "pip-audit==2.9.0" in dockerfile
    assert "python -m pip_audit --local" in dockerfile
    assert ":latest" not in dockerfile


def test_dataflow_container_references_only_materialized_build_context_paths() -> None:
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

    missing_copy = [source for source in copy_sources if not Path(source).exists()]
    missing_flex = [name for name in flex_files if not Path("containers/dataflow", name).exists()]

    assert missing_copy == []
    assert missing_flex == []
    assert Path("containers/dataflow/beam_entrypoint.py").is_file()
    assert Path("containers/dataflow/requirements-dataflow.txt").is_file()


def test_dataflow_write_method_is_not_caller_configurable() -> None:
    entrypoint = Path("containers/dataflow/beam_entrypoint.py").read_text(encoding="utf-8")
    workflow = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")
    runtime = Path("infra/stack/modules/runtime/main.tf").read_text(encoding="utf-8")

    assert "--write_method" not in entrypoint
    assert "write_method:" not in workflow
    assert 'name = "write_method"' not in runtime
    assert "STORAGE_API_AT_LEAST_ONCE" not in entrypoint


def test_flex_template_example_documents_only_supported_parameters() -> None:
    spec = JSON_MAPPING.validate_json(
        Path("contracts/events/dataflow-flex-template-spec.example.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = JSON_MAPPING.validate_python(spec["metadata"])
    parameters = JSON_MAPPINGS.validate_python(metadata["parameters"])
    names: set[str] = set()

    for parameter in parameters:
        name = parameter["name"]
        help_text = parameter["helpText"]
        assert isinstance(name, str)
        assert isinstance(help_text, str)
        assert help_text.strip()
        names.add(name)

    assert metadata["streaming"] is True
    assert names == {
        "input_subscription",
        "valid_table",
        "quarantine_table",
    }


def test_dataflow_entrypoint_when_fixture_runs_matches_bigquery_rows(tmp_path: Path) -> None:
    output_dir = tmp_path / "beam"
    output_dir.mkdir()

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
    assert set(quarantine[0]) == {
        "message_id",
        "ingestion_time",
        "reason_code",
        "event_fingerprint",
        "correlation_id",
    }
    assert quarantine[0]["correlation_id"] == "demo-20260829"
