from pathlib import Path


def test_cli_image_contract_when_docker_builds_project() -> None:
    # Given: the root container definition expected by build automation.
    dockerfile = Path("Dockerfile")
    dockerignore = Path(".dockerignore")

    # When: the machine-consumed build contracts are read.
    assert dockerfile.exists(), "Dockerfile must exist"
    assert dockerignore.exists(), ".dockerignore must exist"
    instructions = dockerfile.read_text(encoding="utf-8").splitlines()
    exclusions = set(dockerignore.read_text(encoding="utf-8").splitlines())

    # Then: the image is multi-stage, locked, non-root and starts the real CLI.
    from_instructions = [line for line in instructions if line.startswith("FROM ")]
    assert len(from_instructions) == 2
    assert "python3.13" in from_instructions[0]
    assert "python:3.13" in from_instructions[1]
    assert "RUN uv sync --frozen --no-dev --no-editable" in instructions
    assert "USER app" in instructions
    assert 'ENTRYPOINT ["alfabetizacao"]' in instructions
    assert {".git", ".venv", ".env", "tests"} <= exclusions
