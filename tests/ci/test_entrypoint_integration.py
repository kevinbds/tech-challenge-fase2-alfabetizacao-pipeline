import os
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict


class SmokeImage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    command: tuple[str, ...]


class SmokeManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    digest_required: bool
    image_unavailable_exit: int
    command_missing_exit: int
    success_exit: int
    timeout_seconds: int
    images: dict[str, SmokeImage]


def test_container_entrypoints_when_integration_gate_is_enabled() -> None:
    # Given: the final integration gate is explicitly enabled by the orchestrator.
    if os.environ.get("ALFABETIZACAO_VERIFY_ENTRYPOINTS") != "1":
        pytest.skip("needs integration: Batch wiring and Streaming demo land on other lanes")
    manifest = SmokeManifest.model_validate_json(
        Path("containers/smoke-contract.json").read_text(encoding="utf-8")
    )
    assert manifest.images["producer"].command == (
        "python",
        "-m",
        "alfabetizacao_pipeline.streaming.producer",
        "--help",
    )

    # When: every specialized image entrypoint is driven through its real local surface.
    results = {
        name: subprocess.run(
            ("uv", "run", "--frozen", "--all-groups", *image.command),
            check=False,
            capture_output=True,
            text=True,
        )
        for name, image in manifest.images.items()
    }

    # Then: a missing command, module or CLI wiring fails final integration.
    failures = {
        name: result.stderr or result.stdout
        for name, result in results.items()
        if result.returncode != 0
    }
    assert failures == {}
