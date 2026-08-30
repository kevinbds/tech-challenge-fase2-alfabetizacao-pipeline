from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    match value:
        case dict() as mapping:
            return mapping
        case _:
            message = "expected a mapping"
            raise AssertionError(message)


def _sequence(value: JsonValue) -> list[JsonValue]:
    match value:
        case list() as sequence:
            return sequence
        case _:
            message = "expected a sequence"
            raise AssertionError(message)


def _load(path: str) -> dict[str, JsonValue]:
    return _mapping(JSON_VALUE.validate_json(Path(path).read_text(encoding="utf-8")))


def test_ci_when_workflow_is_parsed() -> None:
    # Given: the pull-request CI workflow encoded as YAML-compatible JSON.
    workflow = _load(".github/workflows/ci.yml")

    # When: permissions, jobs and action references are inspected structurally.
    permissions = _mapping(workflow["permissions"])
    jobs = _mapping(workflow["jobs"])
    expected_jobs = {"python", "dbt_sql", "terraform", "contracts_docs", "secret_scan"}
    uses: list[str] = []
    for job_name in expected_jobs:
        job = _mapping(jobs[job_name])
        for step_value in _sequence(job["steps"]):
            step = _mapping(step_value)
            action = step.get("uses")
            if isinstance(action, str):
                uses.append(action)

    # Then: CI is least-privilege and every action is pinned to a full SHA.
    assert permissions == {"contents": "read"}
    assert expected_jobs <= jobs.keys()
    assert uses
    assert all("@" in action and len(action.rsplit("@", 1)[1]) == 40 for action in uses)
    assert "pull_request" in _sequence(workflow["on"])


def test_deploy_when_workflow_is_parsed() -> None:
    # Given: the protected, manual deployment workflow.
    workflow = _load(".github/workflows/deploy.yml")

    # When: triggers and job-level authority are inspected.
    jobs = _mapping(workflow["jobs"])
    deploy = _mapping(jobs["deploy"])
    permissions = _mapping(deploy["permissions"])
    serialized = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")

    # Then: deployment is manual, environment-protected, WIF-only and keyless.
    assert workflow["on"] == ["workflow_dispatch"]
    assert deploy["environment"] == "production"
    assert permissions == {"contents": "read", "id-token": "write"}
    assert "workload_identity_provider" in serialized
    assert "service_account" in serialized
    assert "credentials_json" not in serialized
    assert "service_account_key" not in serialized
