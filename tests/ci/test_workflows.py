from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_SEQUENCE: TypeAdapter[list[JsonValue]] = TypeAdapter(list[JsonValue])


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(value)


def _sequence(value: JsonValue) -> list[JsonValue]:
    return JSON_SEQUENCE.validate_python(value)


def _load(path: str) -> dict[str, JsonValue]:
    return _mapping(JSON_VALUE.validate_json(Path(path).read_text(encoding="utf-8")))


def test_ci_when_workflow_is_parsed() -> None:
    workflow = _load(".github/workflows/ci.yml")

    permissions = _mapping(workflow["permissions"])
    jobs = _mapping(workflow["jobs"])
    expected_jobs = {
        "python",
        "dependency_audit",
        "dbt_sql",
        "terraform",
        "contracts_docs",
        "secret_scan",
    }
    uses: list[str] = []
    for job_name in expected_jobs:
        job = _mapping(jobs[job_name])
        for step_value in _sequence(job["steps"]):
            step = _mapping(step_value)
            action = step.get("uses")
            if isinstance(action, str):
                uses.append(action)

    assert permissions == {"contents": "read"}
    assert expected_jobs <= jobs.keys()
    assert uses
    assert all("@" in action and len(action.rsplit("@", 1)[1]) == 40 for action in uses)
    assert "pull_request" in _sequence(workflow["on"])


def test_ci_when_python_dependencies_are_installed_then_audit_is_frozen() -> None:
    workflow = _load(".github/workflows/ci.yml")

    jobs = _mapping(workflow["jobs"])
    python_job = _mapping(jobs["python"])
    dependency_audit_job = _mapping(jobs["dependency_audit"])
    run_commands = [
        command
        for step_value in _sequence(python_job["steps"])
        if isinstance(command := _mapping(step_value).get("run"), str)
    ]

    assert "uv run --frozen pip-audit --local" in run_commands
    audit_commands = [
        command
        for step_value in _sequence(dependency_audit_job["steps"])
        if isinstance(command := _mapping(step_value).get("run"), str)
    ]

    assert (
        "docker build --target dataflow-dependency-audit --file containers/dataflow.Dockerfile ."
    ) in audit_commands


def test_deploy_when_workflow_is_parsed() -> None:
    workflow = _load(".github/workflows/deploy.yml")

    jobs = _mapping(workflow["jobs"])
    deploy = _mapping(jobs["deploy"])
    permissions = _mapping(deploy["permissions"])
    timeout_minutes = deploy["timeout-minutes"]
    serialized = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert workflow["on"] == ["workflow_dispatch"]
    assert deploy["environment"] == "production"
    assert permissions == {"contents": "read", "id-token": "write"}
    assert "workload_identity_provider" in serialized
    assert "service_account" in serialized
    assert "credentials_json" not in serialized
    assert "service_account_key" not in serialized
    assert "GCP_ARTIFACT_BUCKET" in serialized
    assert "GCP_CLOUD_BUILD_SERVICE_ACCOUNT" in serialized
    assert isinstance(timeout_minutes, int)
    assert not isinstance(timeout_minutes, bool)
    assert timeout_minutes >= 60
