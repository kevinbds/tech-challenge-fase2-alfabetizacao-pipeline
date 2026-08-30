import subprocess
import sys
from pathlib import Path

WORKFLOW_GUARD_PROGRAM = """
import sys
import yaml

workflow = yaml.safe_load(sys.stdin.read())
main_steps = workflow["main"]["steps"]
top_level = {next(iter(step)) for step in main_steps}
guarded = next(step["guarded_execution"] for step in main_steps if "guarded_execution" in step)
guarded_names = {next(iter(step)) for step in guarded["try"]["steps"]}
assert "launch_flex" not in top_level
assert {"launch_flex", "remember_job"} <= guarded_names
cleanup_step = next(
    step["cleanup_after_failure"]
    for step in guarded["except"]["steps"]
    if "cleanup_after_failure" in step
)
cleanup_args = cleanup_step["try"]["args"]
assert {"job_id", "job_name", "correlation_id"} <= set(cleanup_args)
cleanup = workflow["cleanup_dataflow"]
assert {"job_id", "job_name", "correlation_id"} <= set(cleanup["params"])
cleanup_steps = cleanup["steps"]
route = next(step["route_by_id"] for step in cleanup_steps if "route_by_id" in step)
assert route["switch"][0]["condition"] == "${job_id != null}"
calls = {
    value["call"]
    for step in cleanup_steps
    for value in step.values()
    if isinstance(value, dict) and "call" in value
}
assert "googleapis.dataflow.v1b3.projects.locations.jobs.list" in calls
listing = next(step["list_active_jobs"] for step in cleanup_steps if "list_active_jobs" in step)
assert listing["args"]["filter"] == "ACTIVE"
assert listing["args"]["pageSize"] == 100
retry = next(step["retry_discovery"] for step in cleanup_steps if "retry_discovery" in step)
assert retry["switch"][0]["condition"] == "${discovery_attempt >= 12}"
pause = next(step["pause_discovery"] for step in cleanup_steps if "pause_discovery" in step)
assert pause["call"] == "sys.sleep"
assert pause["args"]["seconds"] == 10
matcher = next(step["candidate_matches"] for step in cleanup_steps if "candidate_matches" in step)
match_condition = matcher["switch"][0]["condition"]
assert "candidate.name == job_name" in match_condition
assert 'map.get(candidate_labels, "run_id") == correlation_id' in match_condition
"""


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
    assert "additionalUserLabels: {run_id:" in content
    assert "as: workflow_error" in content
    assert "as: cleanup_error" in content
    assert "raise: ${workflow_error}" in content
    assert "queryParameters:" in content
    assert "correlation_id" in content
    assert "window_start" in content
    assert "objects.items[0].updated >= window_start" in content
    assert "projects.locations.operations.get" not in content


def test_flex_launch_and_ambiguous_result_are_inside_guarded_cleanup() -> None:
    # Given the parsed workflow control-flow tree
    content = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")

    # When executable structure is inspected instead of matching loose text
    completed = subprocess.run(
        [sys.executable, "-c", WORKFLOW_GUARD_PROGRAM],
        input=content,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then launch and both known/ambiguous cleanup paths are structurally guarded
    assert completed.returncode == 0, completed.stderr
