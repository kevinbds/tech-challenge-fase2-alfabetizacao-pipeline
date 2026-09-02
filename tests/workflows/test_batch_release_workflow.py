from pathlib import Path

import yaml
from pydantic import JsonValue, TypeAdapter

EXPECTED_SOURCES = {
    "uf",
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "municipio",
    "alunos",
}
JSON_MAPPING = TypeAdapter(dict[str, JsonValue])
JSON_STEPS = TypeAdapter(list[dict[str, JsonValue]])


def test_batch_workflow_owns_one_release_and_waits_through_native_connector_lro() -> None:
    path = Path("infra/stack/modules/runtime/templates/batch.yaml")
    workflow = JSON_MAPPING.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")))
    serialized = path.read_text(encoding="utf-8")

    assert workflow is not None
    assert all(source in serialized for source in EXPECTED_SOURCES)
    assert "input.sources" not in serialized
    assert "release_id" in serialized
    assert "release_nonce" in serialized
    assert '"batch-" + text.substring(execution_month' in serialized
    assert '+ "-y" + string(year) + "-r" +' in serialized

    assert serialized.count("googleapis.run.v2.projects.locations.jobs.run") >= 5
    assert "connector_params:" in serialized
    assert "timeout: 3900" in serialized
    assert "projects.locations.operations.get" not in serialized
    assert "except:" in serialized
    assert "release, fail" in serialized
    assert "list.concat(batch_executions, batch_execution)" in serialized
    assert "list.concat(batch_executions, [batch_execution])" not in serialized
    assert "dbt_build_execution.name" not in serialized
    assert "quality_execution.name" not in serialized
    assert "promotion_execution.name" not in serialized
    assert 'action == "release"' in serialized
    assert "unsupported action" in serialized
    assert "cleanup_error" in serialized
    assert 'year: $${map.get(input, "year")}' in serialized
    assert "year == null or year < 2000 or year > 2100" in serialized
    assert "release year must be between 2000 and 2100" in serialized
    assert 'action == "rollback"' in serialized
    assert serialized.count("next: validate_year") == 2
    assert "next: route_action" in serialized
    assert '"{\\"reference_year\\":" + json.encode_to_string(year) + "}"' in serialized
    assert "action: rollback" in serialized
    assert "year: $${year}" in serialized

    expected_order = (
        "release, begin",
        "batch, run",
        "release, complete",
        "build",
        "evaluate_release",
        "promote_release",
    )
    positions = tuple(serialized.index(marker) for marker in expected_order)
    assert positions == tuple(sorted(positions))


def test_batch_workflow_rejects_non_map_and_non_integer_years_before_dispatch() -> None:
    path = Path("infra/stack/modules/runtime/templates/batch.yaml")
    workflow = JSON_MAPPING.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")))
    main = JSON_MAPPING.validate_python(workflow["main"])
    steps = JSON_STEPS.validate_python(main["steps"])
    names = [next(iter(step)) for step in steps]
    steps_by_name = {
        name: JSON_MAPPING.validate_python(value) for step in steps for name, value in step.items()
    }
    map_guard = JSON_STEPS.validate_python(steps_by_name["require_map_input"]["switch"])
    year_guard = JSON_STEPS.validate_python(steps_by_name["validate_year"]["switch"])
    first_dispatch = names.index("rollback_release")

    assert names.index("require_map_input") < names.index("initialize") < first_dispatch
    assert names.index("validate_year") < first_dispatch
    assert map_guard == [
        {
            "condition": '$${get_type(input) != "map"}',
            "next": "reject_input",
        }
    ]
    assert steps_by_name["reject_input"] == {
        "raise": "workflow input must be a map with action and year",
    }
    assert [branch["condition"] for branch in year_guard] == [
        '$${get_type(year) != "integer"}',
        "$${year == null or year < 2000 or year > 2100}",
    ]
