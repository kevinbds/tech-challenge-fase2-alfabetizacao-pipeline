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
step_by_name = {next(iter(step)): next(iter(step.values())) for step in cleanup_steps}
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
assert listing["args"]["pageToken"] == "${page_token}"
discovery_init = step_by_name["init_discovery"]
init_values = {next(iter(item)): next(iter(item.values())) for item in discovery_init["assign"]}
assert init_values["discovery_scan"] == 1
assert init_values["discovery_deadline"] == "${sys.now() + 120}"
page_init = step_by_name["init_page_scan"]
page_values = {next(iter(item)): next(iter(item.values())) for item in page_init["assign"]}
assert page_values["page_token"] == ""
assert page_values["visited_page_tokens"] == [""]
assert page_values["matched_job_id"] is None
assert page_values["duplicate_match"] is False
next_page = next(step["capture_next_page"] for step in cleanup_steps if "capture_next_page" in step)
assert "nextPageToken" in next_page["assign"][0]["next_page_token"]
page_guard = next(step["guard_next_page"] for step in cleanup_steps if "guard_next_page" in step)
page_conditions = {branch["condition"] for branch in page_guard["switch"]}
assert "${next_page_token in visited_page_tokens}" in page_conditions
assert "${page_count >= 100}" in page_conditions
assert any(
    "sys.now()" in condition and "discovery_deadline" in condition
    for condition in page_conditions
)
retry = next(step["retry_discovery"] for step in cleanup_steps if "retry_discovery" in step)
assert retry["switch"][0]["condition"] == (
    "${discovery_scan >= 12 or sys.now() >= discovery_deadline}"
)
pause = next(step["pause_discovery"] for step in cleanup_steps if "pause_discovery" in step)
assert pause["call"] == "sys.sleep"
assert pause["args"]["seconds"] == 10
matcher = next(step["candidate_matches"] for step in cleanup_steps if "candidate_matches" in step)
match_condition = matcher["switch"][0]["condition"]
assert "candidate.name == job_name" in match_condition
assert 'map.get(candidate_labels, "run_id") == correlation_id' in match_condition
assert matcher["switch"][0]["next"] != "remember_discovered"
assert "record_match" in step_by_name
assert "record_duplicate" in step_by_name
assert "choose_unique_match" in step_by_name
unique_branches = step_by_name["choose_unique_match"]["switch"]
unique_conditions = {branch["condition"] for branch in unique_branches}
assert "${duplicate_match}" in unique_conditions
assert "${matched_job_id != null}" in unique_conditions
duplicate_target = next(
    branch["next"]
    for branch in unique_branches
    if branch["condition"] == "${duplicate_match}"
)
assert duplicate_target == "no_matching_job"
unique_target = next(
    branch["next"]
    for branch in unique_branches
    if branch["condition"] == "${matched_job_id != null}"
)
assert unique_target == "remember_discovered"
assert step_by_name["validate_listing"]["switch"][0]["next"] == "no_matching_job"
assert step_by_name["validate_candidate"]["switch"][0]["next"] == "no_matching_job"
assert step_by_name["validate_next_page"]["switch"][0]["next"] == "no_matching_job"
cycle_branch = next(
    branch for branch in step_by_name["guard_next_page"]["switch"]
    if branch["condition"] == "${next_page_token in visited_page_tokens}"
)
assert cycle_branch["next"] == "no_matching_job"
advance_page_values = {
    next(iter(item)): next(iter(item.values()))
    for item in step_by_name["advance_page"]["assign"]
}
assert advance_page_values["visited_page_tokens"] == (
    "${list.concat(visited_page_tokens, next_page_token)}"
)
advance_scan = step_by_name["advance_discovery"]
assert advance_scan["assign"] == [{"discovery_scan": "${discovery_scan + 1}"}]
assert advance_scan["next"] == "init_page_scan"
assert step_by_name["pause_discovery"]["next"] == "advance_discovery"
assert step_by_name["remember_discovered"]["assign"] == [{"job_id": "${matched_job_id}"}]
assert step_by_name["cancel"]["args"]["jobId"] == "${job_id}"
for step_name in ("list_active_jobs", "cancel"):
    assert step_by_name[step_name]["args"]["connector_params"]["timeout"] > 0
drain = next(step["request_drain"] for step in guarded["try"]["steps"] if "request_drain" in step)
assert drain["args"]["connector_params"]["timeout"] > 0
build_stream = next(
    step["build_stream_models"]
    for step in guarded["try"]["steps"]
    if "build_stream_models" in step
)
assert build_stream["call"] == "googleapis.run.v2.projects.locations.jobs.run"
assert build_stream["args"]["name"] == "${args.dbt_job_name}"
assert build_stream["args"]["connector_params"]["timeout"] == 3600
build_args = build_stream["args"]["body"]["overrides"]["containerOverrides"][0]["args"]
assert "tag:stream_demo" in build_args
guarded_except = guarded["except"]["steps"]
cleanup_guard = next(
    step["cleanup_after_failure"]
    for step in guarded_except
    if "cleanup_after_failure" in step
)
assert "except" in cleanup_guard
preserve = next(step["preserve_failure"] for step in guarded_except if "preserve_failure" in step)
assert preserve["raise"] == "${workflow_error}"
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
    assert "merge_and_test_sql" not in content


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
