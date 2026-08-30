from pathlib import Path


def test_makefile_when_targets_are_indexed() -> None:
    # Given: the local operator Makefile.
    lines = Path("Makefile").read_text(encoding="utf-8").splitlines()

    # When: concrete target names are indexed without reading help prose.
    targets = {
        line.split(":", maxsplit=1)[0]
        for line in lines
        if line and not line.startswith(("\t", ".", "#")) and ":" in line
    }

    # Then: fast/full verification and local FinOps surfaces are executable.
    assert {"help", "verify-fast", "verify", "test-ops", "test-ci", "estimate-cost"} <= targets
    assert "deploy" not in targets
