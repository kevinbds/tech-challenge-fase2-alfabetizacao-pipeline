from pathlib import Path

import yaml
from pydantic import JsonValue, TypeAdapter

JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def test_stream_demo_passes_required_release_year_to_producer() -> None:
    workflow = JSON_MAPPING.validate_python(
        JSON_VALUE.validate_python(
            yaml.safe_load(Path("workflows/stream_demo.yaml").read_text(encoding="utf-8"))
        )
    )
    main = JSON_MAPPING.validate_python(workflow["main"])
    steps = TypeAdapter(list[dict[str, JsonValue]]).validate_python(main["steps"])

    read_input = JSON_MAPPING.validate_python(
        next(step["read_input"] for step in steps if "read_input" in step)
    )
    assignments = TypeAdapter(list[dict[str, JsonValue]]).validate_python(read_input["assign"])
    assigned = {key: value for item in assignments for key, value in item.items()}
    guarded = JSON_MAPPING.validate_python(
        next(step["guarded_execution"] for step in steps if "guarded_execution" in step)
    )
    guarded_try = JSON_MAPPING.validate_python(guarded["try"])
    guarded_steps = TypeAdapter(list[dict[str, JsonValue]]).validate_python(guarded_try["steps"])
    publish_fixture = JSON_MAPPING.validate_python(
        next(step["publish_fixture"] for step in guarded_steps if "publish_fixture" in step)
    )
    publish_args = JSON_MAPPING.validate_python(publish_fixture["args"])
    connector_params = JSON_MAPPING.validate_python(publish_args["connector_params"])
    serialized = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")

    assert assigned["release_year"] == '${map.get(args, "release_year")}'
    assert "--year, '${string(release_year)}'" in serialized
    assert "name: CORRELATION_ID" in serialized
    assert "--correlation-id" not in serialized
    assert connector_params["timeout"] == 990


def test_monthly_batch_requires_explicit_year_without_clock_fallback() -> None:
    template = Path("infra/stack/modules/runtime/templates/batch.yaml").read_text(encoding="utf-8")

    assert 'year: $${map.get(input, "year")}' in template
    assert "year == null or year < 2000 or year > 2100" in template
    assert "year: $${time." not in template
    assert "year: $${sys." not in template


def test_runtime_passes_full_topic_identifier_to_producer() -> None:
    runtime = Path("infra/stack/runtime.tf").read_text(encoding="utf-8")

    assert "stream_topic_name        = module.streaming.topic_id" in runtime
