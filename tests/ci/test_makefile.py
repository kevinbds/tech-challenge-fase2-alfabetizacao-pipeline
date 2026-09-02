from pathlib import Path


def test_makefile_when_targets_are_indexed() -> None:
    lines = Path("Makefile").read_text(encoding="utf-8").splitlines()

    targets = {
        line.split(":", maxsplit=1)[0]
        for line in lines
        if line and not line.startswith(("\t", ".", "#")) and ":" in line
    }

    assert {"help", "verify-fast", "verify", "test-ops", "test-ci", "estimate-cost"} <= targets
    assert "deploy" not in targets


def test_makefile_when_ops_coverage_runs_includes_yaml_lint_tests() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    test_recipe = content.split("test-ops: ##", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

    assert "pytest tests/ops tests/ci/test_yaml_lint.py" in test_recipe
