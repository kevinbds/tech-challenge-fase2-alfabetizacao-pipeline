import subprocess
import sys


def test_sqlfluff_streaming_passes_from_repository_root_without_extra_config_flag() -> None:
    # Given the repository-root SQLFluff configuration
    # When the normal root invocation lints streaming SQL
    completed = subprocess.run(
        [sys.executable, "-m", "sqlfluff", "lint", "sql/streaming"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then standalone SQL never depends on an absent dbt project/profile
    assert completed.returncode == 0, completed.stdout + completed.stderr
