import subprocess
import sys
from pathlib import Path


def test_workflow_is_structurally_valid_and_bounded() -> None:
    # Given the deployable workflow artifact
    path = Path("workflows/stream_demo.yaml")
    content = path.read_text(encoding="utf-8")

    # When a real YAML parser loads it
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys,yaml; data=yaml.safe_load(sys.stdin.read()); assert 'main' in data",
        ],
        input=content,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then all bounded lifecycle and independent evidence stages are present
    assert completed.returncode == 0
    assert "max_attempts: 90" in content
    assert "max_attempts: 60" in content
    assert "max_attempts: 120" in content
    assert "requestedState: JOB_STATE_DRAINED" in content
    assert "requestedState: JOB_STATE_CANCELLED" in content
    assert "raw_archive_branch" in content
    assert "backlog_and_dlq_assert_sql" in content
    assert "additionalExperiments: [enable_portable_runner]" in content
