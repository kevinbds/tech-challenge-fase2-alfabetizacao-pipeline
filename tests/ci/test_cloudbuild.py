from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_SEQUENCE: TypeAdapter[list[JsonValue]] = TypeAdapter(list[JsonValue])


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(value)


def _sequence(value: JsonValue) -> list[JsonValue]:
    return JSON_SEQUENCE.validate_python(value)


def test_cloudbuild_when_definition_is_parsed() -> None:
    # Given: the versioned Cloud Build definition.
    path = Path("cloudbuild/build-images.yml")
    config = _mapping(JSON_VALUE.validate_json(path.read_text(encoding="utf-8")))

    # When: machine-consumed build steps and substitutions are inspected.
    substitutions = _mapping(config["substitutions"])
    steps = [_mapping(step) for step in _sequence(config["steps"])]
    step_ids = {str(step["id"]) for step in steps}
    serialized = path.read_text(encoding="utf-8")
    digest_capture = Path("cloudbuild/capture-digests.sh").read_text(encoding="utf-8")

    # Then: builds are SHA-tagged, digest-producing, keyless and provenance-aware.
    assert substitutions["_SERVICE_ACCOUNT"] == ""
    assert substitutions["_REGION"] == "southamerica-east1"
    assert all("latest" not in str(step) for step in steps)
    assert all("@sha256:" in str(step["name"]) for step in steps)
    assert {
        "build-batch",
        "push-batch",
        "build-dbt",
        "push-dbt",
        "build-producer",
        "push-producer",
        "build-dataflow",
        "push-dataflow",
        "capture-digests",
    } == step_ids
    assert all(f'"{image}"' in digest_capture for image in ("batch", "dbt", "producer", "dataflow"))
    assert "$COMMIT_SHA" in serialized
    assert "image-digests.json" in serialized
    assert "sha256" in digest_capture
    assert "cloudbuild/capture-digests.sh" in serialized
    assert all(name in serialized for name in ("PROJECT_ID", "COMMIT_SHA", "BUILD_ID"))
    assert "requestedVerifyOption" in serialized
    assert "credentials" not in serialized.lower()
    assert "key.json" not in serialized.lower()
