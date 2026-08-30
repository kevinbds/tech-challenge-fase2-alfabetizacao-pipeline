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
    # Given: one specialized runtime image contract.
    instructions = Path(f"containers/{name}.Dockerfile").read_text(encoding="utf-8").splitlines()

    # When: Docker instructions are classified.
    from_lines = [line for line in instructions if line.startswith("FROM ")]
    entrypoints = [line for line in instructions if line.startswith("ENTRYPOINT ")]
    users = [line for line in instructions if line.startswith("USER ")]

    # Then: the image is multi-stage, digest-pinned, locked and non-root.
    assert len(from_lines) == 2
    assert all("@sha256:" in line for line in from_lines)
    assert all(":latest" not in line for line in from_lines)
    assert any("uv sync --frozen" in line for line in instructions)
    assert users[-1] == "USER app"
    assert entrypoints == [f"ENTRYPOINT {entrypoint}"]
    assert all("COPY .env" not in line and "key.json" not in line for line in instructions)


def test_container_contract_when_manifest_is_loaded() -> None:
    # Given: the smoke contract which distinguishes image and command failures.
    text = Path("containers/smoke-contract.json").read_text(encoding="utf-8")

    # When/Then: both failure classes and digest enforcement are explicit machine fields.
    assert '"image_unavailable_exit": 125' in text
    assert '"command_missing_exit": 127' in text
    assert '"digest_required": true' in text


def test_producer_image_when_fixture_is_required_at_runtime() -> None:
    # Given: the producer publishes the versioned deterministic fixture.
    instructions = Path("containers/producer.Dockerfile").read_text(encoding="utf-8")

    # When/Then: the runtime image materializes that fixture under its declared path.
    assert "contracts/events/fixtures/demo.json" in instructions
