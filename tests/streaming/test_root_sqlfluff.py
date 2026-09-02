import subprocess
import sys


def test_sqlfluff_streaming_passes_from_repository_root_without_extra_config_flag() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "sqlfluff", "lint", "sql/streaming"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
