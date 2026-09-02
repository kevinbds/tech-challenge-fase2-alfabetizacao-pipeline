from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class SmokeCheck(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    name: str
    arguments: tuple[str, ...]
    expected_exit: int
    docker_entrypoint: str | None = None


class SmokeImage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    entrypoint: tuple[str, ...]
    checks: tuple[SmokeCheck, ...]


class SmokeManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    digest_required: bool
    timeout_seconds: int
    images: dict[str, SmokeImage]


def test_runtime_smoke_manifest_declares_required_entrypoints() -> None:
    manifest = SmokeManifest.model_validate_json(
        Path("containers/smoke-contract.json").read_text(encoding="utf-8")
    )
    assert manifest.version == "2.0"
    assert manifest.digest_required is True
    assert manifest.images["producer"].entrypoint == (
        "python",
        "-m",
        "alfabetizacao_pipeline.streaming.producer",
    )
    assert manifest.images["dataflow_template"].entrypoint == (
        "/opt/google/dataflow/python_template_launcher",
    )
    assert manifest.images["dataflow_template"].checks[0].arguments == ("--help",)
    assert manifest.images["dataflow_template"].checks[0].docker_entrypoint is None
    assert manifest.images["dataflow_sdk"].entrypoint == ("/opt/apache/beam/boot",)
    assert manifest.images["dataflow_sdk"].checks[0].arguments == ("--help",)
    assert manifest.images["dataflow_sdk"].checks[0].docker_entrypoint is None
