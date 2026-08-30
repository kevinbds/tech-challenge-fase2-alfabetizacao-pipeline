import subprocess
import sys
from pathlib import Path

import pytest

from alfabetizacao_pipeline.ops.yaml_lint import (
    MissingYamlPathError,
    run_yaml_lint,
    select_yaml_paths,
)


def test_yaml_lint_when_repository_surfaces_are_selected() -> None:
    # Given: the same module invoked by CI from the repository root.
    command = (sys.executable, "-m", "alfabetizacao_pipeline.ops.yaml_lint")

    # When: the pinned yamllint verifier runs against real files.
    result = subprocess.run(command, check=False, capture_output=True, text=True)

    # Then: syntax, configured rules and path selection all pass together.
    assert result.returncode == 0, result.stdout + result.stderr


def test_yaml_paths_when_integrated_workflows_exist(tmp_path: Path) -> None:
    # Given: all required surfaces and a workflows directory from another lane.
    for name in (".github", "cloudbuild", "ops", "workflows"):
        (tmp_path / name).mkdir()

    # When: selection is evaluated.
    selected = select_yaml_paths(tmp_path)

    # Then: workflows participates instead of being silently omitted.
    assert selected == tuple(
        tmp_path / name for name in (".github", "cloudbuild", "ops", "workflows")
    )


def test_yaml_paths_when_required_surface_is_missing(tmp_path: Path) -> None:
    # Given: an incomplete checkout missing required platform configuration.
    (tmp_path / ".github").mkdir()
    (tmp_path / "cloudbuild").mkdir()

    # When/Then: selection fails instead of turning the lint gate green.
    with pytest.raises(MissingYamlPathError):
        _ = select_yaml_paths(tmp_path)


def test_yaml_lint_when_integrated_workflow_is_malformed(tmp_path: Path) -> None:
    # Given: valid required surfaces and one malformed integrated workflow.
    for name in (".github", "cloudbuild", "ops", "workflows"):
        directory = tmp_path / name
        directory.mkdir()
        _ = (directory / "valid.yml").write_text("{}\n", encoding="utf-8")
    _ = (tmp_path / "workflows" / "invalid.yml").write_text("[\n", encoding="utf-8")
    _ = (tmp_path / ".yamllint.yml").write_text(
        Path(".yamllint.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # When: the same pinned verifier used by CI runs in the integrated tree.
    exit_code = run_yaml_lint(tmp_path)

    # Then: workflows is linted and the real syntax error propagates.
    assert exit_code != 0
