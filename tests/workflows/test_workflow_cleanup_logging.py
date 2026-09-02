from pathlib import Path

import yaml
from pydantic import JsonValue, TypeAdapter

JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_STEPS: TypeAdapter[list[dict[str, JsonValue]]] = TypeAdapter(list[dict[str, JsonValue]])


def _steps_by_name(path: Path) -> dict[str, dict[str, JsonValue]]:
    workflow = JSON_MAPPING.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")))
    main = JSON_MAPPING.validate_python(workflow["main"])
    steps = JSON_STEPS.validate_python(main["steps"])
    return {
        name: JSON_MAPPING.validate_python(value) for step in steps for name, value in step.items()
    }


def _exception_steps(step: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    exception = JSON_MAPPING.validate_python(step["except"])
    steps = JSON_STEPS.validate_python(exception["steps"])
    return {
        name: JSON_MAPPING.validate_python(value) for item in steps for name, value in item.items()
    }


def test_batch_cleanup_logging_cannot_replace_the_release_failure() -> None:
    steps = _steps_by_name(Path("infra/stack/modules/runtime/templates/batch.yaml"))
    release_try = JSON_MAPPING.validate_python(steps["guarded_release"]["try"])
    release_steps = JSON_STEPS.validate_python(release_try["steps"])
    release_step_names = [next(iter(step)) for step in release_steps]
    release_steps_by_name = {
        name: JSON_MAPPING.validate_python(value)
        for step in release_steps
        for name, value in step.items()
    }
    release_handler = _exception_steps(steps["guarded_release"])
    armed_handler = JSON_MAPPING.validate_python(release_handler["fail_if_armed"])
    armed_branches = JSON_STEPS.validate_python(armed_handler["switch"])

    assert release_step_names.index("arm_release_cleanup") < release_step_names.index(
        "begin_release"
    )
    assert release_steps_by_name["arm_release_cleanup"] == {
        "assign": [{"release_cleanup_armed": True}]
    }
    assert armed_branches[0] == {
        "condition": "$${release_cleanup_armed}",
        "next": "fail_release",
    }
    cleanup_handler = _exception_steps(release_handler["fail_release"])
    logging_guard = JSON_MAPPING.validate_python(cleanup_handler["log_cleanup_error"])
    logging_handler = _exception_steps(logging_guard)
    logging_try = JSON_MAPPING.validate_python(logging_guard["try"])
    log_call = JSON_MAPPING.validate_python(
        JSON_STEPS.validate_python(logging_try["steps"])[0]["write_cleanup_log"]
    )
    log_args = JSON_MAPPING.validate_python(log_call["args"])

    assert log_call["call"] == "sys.log"
    assert set(log_args) == {"severity", "text"}
    assert logging_handler["preserve_release_after_logging_failure"] == {
        "raise": "$${release_error}"
    }
    assert cleanup_handler["preserve_release_after_cleanup"] == {"raise": "$${release_error}"}


def test_stream_cleanup_logging_cannot_replace_the_workflow_failure() -> None:
    steps = _steps_by_name(Path("workflows/stream_demo.yaml"))
    workflow_handler = _exception_steps(steps["guarded_execution"])
    cleanup_handler = _exception_steps(workflow_handler["cleanup_after_failure"])
    logging_guard = JSON_MAPPING.validate_python(cleanup_handler["record_cleanup_failure"])
    logging_handler = _exception_steps(logging_guard)
    logging_try = JSON_MAPPING.validate_python(logging_guard["try"])
    log_call = JSON_MAPPING.validate_python(
        JSON_STEPS.validate_python(logging_try["steps"])[0]["write_cleanup_log"]
    )
    log_args = JSON_MAPPING.validate_python(log_call["args"])

    assert log_call["call"] == "sys.log"
    assert set(log_args) == {"severity", "text"}
    assert logging_handler["preserve_workflow_error"] == {"raise": "${workflow_error}"}
    assert workflow_handler["preserve_failure"] == {"raise": "${workflow_error}"}
