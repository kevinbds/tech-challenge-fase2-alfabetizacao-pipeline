from pathlib import Path
from typing import Final

import yaml
from pydantic import JsonValue, TypeAdapter

WORKFLOW_PATH: Final = Path("workflows/stream_demo.yaml")
RUNTIME_TEMPLATE_PATH: Final = Path("infra/stack/modules/runtime/templates/stream-demo.yaml")
JSON_MAPPING: Final = TypeAdapter(dict[str, JsonValue])
JSON_STEPS: Final = TypeAdapter(list[dict[str, JsonValue]])
JSON_VALUES: Final = TypeAdapter(list[JsonValue])
JSON_INTEGER: Final = TypeAdapter(int)


def _workflow() -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")))


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(value)


def _named_steps(raw_steps: JsonValue) -> dict[str, dict[str, JsonValue]]:
    return {
        name: _mapping(step)
        for item in JSON_STEPS.validate_python(raw_steps)
        for name, step in item.items()
    }


def _assigned_values(step: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        name: value
        for assignment in JSON_STEPS.validate_python(step["assign"])
        for name, value in assignment.items()
    }


def _routes(step: dict[str, JsonValue]) -> dict[str, str]:
    return {
        str(branch["condition"]): str(branch["next"])
        for branch in JSON_STEPS.validate_python(step["switch"])
    }


def _parallel_branches(step: dict[str, JsonValue]) -> dict[str, dict[str, dict[str, JsonValue]]]:
    parallel = _mapping(step["parallel"])
    return {
        name: _named_steps(_mapping(branch)["steps"])
        for item in JSON_STEPS.validate_python(parallel["branches"])
        for name, branch in item.items()
    }


def test_canonical_stream_workflow_has_no_driftable_runtime_copy() -> None:
    workflow = _workflow()

    assert "main" in workflow
    assert WORKFLOW_PATH.is_file()
    assert not RUNTIME_TEMPLATE_PATH.exists()


def test_stream_workflow_runs_correlated_dataflow_lifecycle_with_failure_cleanup() -> None:
    workflow = _workflow()
    main = _mapping(workflow["main"])
    main_steps = _named_steps(main["steps"])
    init_values = _assigned_values(main_steps["init"])
    guarded_execution = _mapping(main_steps["guarded_execution"])
    guarded_steps = _named_steps(_mapping(guarded_execution["try"])["steps"])

    assert init_values["correlation_id"] == "${uuid.generate()}"
    assert init_values["job_name"] == (
        '${"literacy-demo-" + text.substring(text.replace_all(correlation_id, "-", ""), 0, 24)}'
    )
    assert {"launch_flex", "remember_job", "request_drain", "build_stream_models"} <= set(
        guarded_steps
    )

    launch = guarded_steps["launch_flex"]
    launch_args = _mapping(launch["args"])
    launch_parameter = _mapping(_mapping(launch_args["body"])["launchParameter"])
    launch_environment = _mapping(launch_parameter["environment"])
    drain = guarded_steps["request_drain"]
    drain_args = _mapping(drain["args"])
    drain_body = _mapping(drain_args["body"])
    wait_drained_args = _mapping(guarded_steps["wait_drained"]["args"])
    build_stream_args = _mapping(guarded_steps["build_stream_models"]["args"])
    build_override = _mapping(_mapping(build_stream_args["body"])["overrides"])
    build_containers = JSON_STEPS.validate_python(build_override["containerOverrides"])
    build_container = build_containers[0]

    assert launch["call"] == "googleapis.dataflow.v1b3.projects.locations.flexTemplates.launch"
    assert _mapping(launch_environment["additionalUserLabels"]) == {"run_id": "${correlation_id}"}
    assert drain["call"] == "googleapis.dataflow.v1b3.projects.locations.jobs.update"
    assert drain_body["requestedState"] == "JOB_STATE_DRAINED"
    assert JSON_INTEGER.validate_python(_mapping(drain_args["connector_params"])["timeout"]) > 0
    assert wait_drained_args["max_attempts"] == 90
    assert build_stream_args["name"] == "${dbt_job_name}"
    assert _mapping(build_stream_args["connector_params"])["timeout"] == 3900
    assert "tag:stream_demo" in JSON_VALUES.validate_python(build_container["args"])

    stage_branches = _parallel_branches(guarded_steps["independent_stage_checks"])
    evidence_branches = _parallel_branches(guarded_steps["check_final_evidence"])
    raw_wait_args = _mapping(stage_branches["raw_archive_branch"]["wait_raw_avro"]["args"])
    backlog_wait_args = _mapping(evidence_branches["backlog_branch"]["wait_main_backlogs"]["args"])

    assert raw_wait_args["max_attempts"] == 18
    assert raw_wait_args["max_pages"] == 10
    assert backlog_wait_args["max_attempts"] == 36

    failure_steps = _named_steps(_mapping(guarded_execution["except"])["steps"])
    cleanup = _mapping(failure_steps["cleanup_after_failure"])
    cleanup_try = _mapping(cleanup["try"])
    cleanup_args = _mapping(cleanup_try["args"])

    assert cleanup_try["call"] == "cleanup_dataflow"
    assert {"job_id", "job_name", "correlation_id"} <= set(cleanup_args)
    assert failure_steps["preserve_failure"] == {"raise": "${workflow_error}"}


def test_cleanup_dataflow_graph_bounds_discovery_and_cancels_only_unique_match() -> None:
    workflow = _workflow()
    cleanup_dataflow = _mapping(workflow["cleanup_dataflow"])
    cleanup_steps = _named_steps(cleanup_dataflow["steps"])
    route_by_id = _routes(cleanup_steps["route_by_id"])
    listing = cleanup_steps["list_active_jobs"]
    listing_args = _mapping(listing["args"])
    discovery_values = _assigned_values(cleanup_steps["init_discovery"])
    page_values = _assigned_values(cleanup_steps["init_page_scan"])
    page_routes = _routes(cleanup_steps["guard_next_page"])
    candidate_routes = _routes(cleanup_steps["candidate_matches"])
    unique_routes = _routes(cleanup_steps["choose_unique_match"])
    retry_routes = _routes(cleanup_steps["retry_discovery"])
    cancel = cleanup_steps["cancel"]
    cancel_args = _mapping(cancel["args"])
    cancelled_wait_args = _mapping(cleanup_steps["wait_cancelled"]["args"])

    assert cleanup_dataflow["params"] == [
        "project_id",
        "region",
        "job_id",
        "job_name",
        "correlation_id",
    ]
    assert route_by_id == {"${job_id != null}": "inspect_known"}
    assert cleanup_steps["route_by_id"]["next"] == "init_discovery"
    assert listing["call"] == "googleapis.dataflow.v1b3.projects.locations.jobs.list"
    assert listing_args["filter"] == "ACTIVE"
    assert listing_args["pageSize"] == 100
    assert JSON_INTEGER.validate_python(_mapping(listing_args["connector_params"])["timeout"]) > 0
    assert discovery_values == {
        "discovery_scan": 1,
        "discovery_deadline": "${sys.now() + 120}",
    }
    assert {
        "page_token": "",
        "visited_page_tokens": [""],
        "matched_job_id": None,
        "duplicate_match": False,
    }.items() <= page_values.items()
    assert page_routes == {
        "${sys.now() >= discovery_deadline}": "no_matching_job",
        '${next_page_token == ""}': "choose_unique_match",
        "${next_page_token in visited_page_tokens}": "no_matching_job",
        "${page_count >= 10}": "retry_discovery",
    }
    assert cleanup_steps["guard_next_page"]["next"] == "advance_page"
    (candidate_condition,) = candidate_routes
    assert candidate_routes[candidate_condition] == "classify_match"
    assert "candidate.name == job_name" in candidate_condition
    assert 'map.get(candidate_labels, "run_id") == correlation_id' in candidate_condition
    assert unique_routes == {
        "${duplicate_match}": "no_matching_job",
        "${matched_job_id != null}": "remember_discovered",
    }
    assert cleanup_steps["choose_unique_match"]["next"] == "retry_discovery"
    assert retry_routes == {
        "${discovery_scan >= 12 or sys.now() >= discovery_deadline}": "no_matching_job"
    }
    assert cleanup_steps["retry_discovery"]["next"] == "pause_discovery"
    assert cleanup_steps["pause_discovery"] == {
        "call": "sys.sleep",
        "args": {"seconds": 10},
        "next": "advance_discovery",
    }
    assert _assigned_values(cleanup_steps["advance_discovery"]) == {
        "discovery_scan": "${discovery_scan + 1}"
    }
    assert cleanup_steps["advance_discovery"]["next"] == "init_page_scan"
    assert cancel["call"] == "googleapis.dataflow.v1b3.projects.locations.jobs.update"
    assert _mapping(cancel_args["body"])["requestedState"] == "JOB_STATE_CANCELLED"
    assert JSON_INTEGER.validate_python(_mapping(cancel_args["connector_params"])["timeout"]) > 0
    assert cancelled_wait_args["max_attempts"] == 60
