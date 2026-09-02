import subprocess
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JQ_IMAGE = (
    "ghcr.io/jqlang/jq@sha256:4f34c6d23f4b1372ac789752cc955dc67c2ae177eb1b5860b75cdc5091ce6f91"
)
JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
STRING: TypeAdapter[str] = TypeAdapter(str)
STRING_MAPPING: TypeAdapter[dict[str, str]] = TypeAdapter(dict[str, str])


def test_capture_when_cloud_build_returns_built_image_objects() -> None:
    root = Path.cwd()
    fixture = Path("tests/fixtures/cloudbuild/build-success.json")

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--volume",
            f"{root}:/workspace:ro",
            "--entrypoint",
            "/jq",
            JQ_IMAGE,
            "-ce",
            "-f",
            "/workspace/cloudbuild/capture-digests.jq",
        ],
        check=True,
        capture_output=True,
        input=fixture.read_text(encoding="utf-8"),
        text=True,
    )

    captured = JSON_MAPPING.validate_json(result.stdout)
    git_sha = STRING.validate_python(captured["git_sha"])
    images = STRING_MAPPING.validate_python(captured["images"])
    assert git_sha == "0123456789abcdef0123456789abcdef01234567"
    assert set(images) == {
        "batch",
        "dbt",
        "producer",
        "dataflow_template",
        "dataflow_sdk",
    }
    assert all("@sha256:" in image for image in images.values())
