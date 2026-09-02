from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("name", "entrypoint"),
    [
        ("batch", '["alfabetizacao", "batch", "run"]'),
        ("dbt", '["dbt"]'),
        ("producer", '["python", "-m", "alfabetizacao_pipeline.streaming.producer"]'),
    ],
)
def test_specialized_image_when_dockerfile_is_parsed(name: str, entrypoint: str) -> None:
    instructions = Path(f"containers/{name}.Dockerfile").read_text(encoding="utf-8").splitlines()

    from_lines = [line for line in instructions if line.startswith("FROM ")]
    entrypoints = [line for line in instructions if line.startswith("ENTRYPOINT ")]
    users = [line for line in instructions if line.startswith("USER ")]

    assert len(from_lines) == 2
    assert all("@sha256:" in line for line in from_lines)
    assert all(":latest" not in line for line in from_lines)
    assert any("uv sync --frozen" in line for line in instructions)
    assert users[-1] == "USER app"
    assert entrypoints == [f"ENTRYPOINT {entrypoint}"]
    assert all("COPY .env" not in line and "key.json" not in line for line in instructions)


def test_container_contract_when_manifest_is_loaded() -> None:
    text = Path("containers/smoke-contract.json").read_text(encoding="utf-8")

    assert '"digest_required": true' in text
    assert '"timeout_seconds": 60' in text
    assert '"dataflow_template"' in text
    assert '"entrypoint": ["/opt/google/dataflow/python_template_launcher"]' in text
    assert '"dataflow_sdk"' in text
    assert '"entrypoint": ["/opt/apache/beam/boot"]' in text


def test_dataflow_image_exposes_distinct_final_role_targets() -> None:
    instructions = Path("containers/dataflow.Dockerfile").read_text(encoding="utf-8")

    assert "AS dataflow-template" in instructions
    assert 'ENTRYPOINT ["/opt/google/dataflow/python_template_launcher"]' in instructions
    assert "AS dataflow-sdk" in instructions
    assert 'ENTRYPOINT ["/opt/apache/beam/boot"]' in instructions


def test_producer_image_when_fixture_is_required_at_runtime() -> None:
    instructions = Path("containers/producer.Dockerfile").read_text(encoding="utf-8")

    assert "contracts/events/fixtures/demo.json" in instructions


def test_runtime_assets_remain_in_the_docker_build_context() -> None:
    ignored_paths = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {"contracts", "dbt"}.isdisjoint(ignored_paths)


def test_dbt_local_artifacts_are_excluded_from_runtime_images() -> None:
    ignored_paths = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {"dbt/target", "dbt/logs", "dbt/.user.yml"}.issubset(ignored_paths)
