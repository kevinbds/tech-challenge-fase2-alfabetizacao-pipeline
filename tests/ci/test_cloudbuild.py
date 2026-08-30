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


def test_cloudbuild_when_definition_is_parsed() -> None:
    # Given: the versioned Cloud Build definition.
    path = Path("cloudbuild/build-images.yml")
    config = _mapping(JSON_VALUE.validate_json(path.read_text(encoding="utf-8")))

    # When: machine-consumed build steps and substitutions are inspected.
    substitutions = _mapping(config["substitutions"])
    steps = [_mapping(step) for step in _sequence(config["steps"])]
    serialized = path.read_text(encoding="utf-8")
    digest_capture = Path("cloudbuild/capture-digests.sh").read_text(encoding="utf-8")

    # Then: builds are SHA-tagged, digest-producing, keyless and provenance-aware.
    assert substitutions["_SERVICE_ACCOUNT"] == ""
    assert substitutions["_REGION"] == "southamerica-east1"
    assert all("latest" not in str(step) for step in steps)
    assert "$COMMIT_SHA" in serialized
    assert "image-digests.json" in serialized
    assert "sha256" in digest_capture
    assert "cloudbuild/capture-digests.sh" in serialized
    assert all(name in serialized for name in ("PROJECT_ID", "COMMIT_SHA", "BUILD_ID"))
    assert "requestedVerifyOption" in serialized
    assert "credentials" not in serialized.lower()
    assert "key.json" not in serialized.lower()
