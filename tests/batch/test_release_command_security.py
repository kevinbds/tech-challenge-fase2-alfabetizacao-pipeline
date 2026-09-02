import json

import pytest
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch import commands
from alfabetizacao_pipeline.batch.commands import app
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution
from alfabetizacao_pipeline.config import AppSettings


class ReleaseCommandStore:
    def begin(self, execution: ReleaseExecution) -> None:
        del execution

    def complete(self, execution: ReleaseExecution) -> None:
        del execution

    def fail(self, execution: ReleaseExecution) -> None:
        del execution


@pytest.mark.parametrize("command", ["begin", "complete", "fail"])
def test_release_commands_emit_only_the_public_release_identity(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    def release_store(_settings: AppSettings) -> ReleaseCommandStore:
        return ReleaseCommandStore()

    monkeypatch.setattr(commands, "_release_store", release_store)

    result = CliRunner().invoke(
        app,
        [
            "release",
            command,
            "--release-id",
            "batch-202608-y2024-r0123456789ab",
            "--year",
            "2024",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "release_id": "batch-202608-y2024-r0123456789ab",
        "year": 2024,
    }
