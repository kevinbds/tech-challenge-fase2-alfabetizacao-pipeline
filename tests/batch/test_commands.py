from pathlib import Path

from typer.testing import CliRunner

from alfabetizacao_pipeline.batch.commands import app
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchPlan, SourceInspection


def test_plan_command_returns_json_and_zero_writes_when_dry_run() -> None:
    # Given: a supported source below the default cap
    runner = CliRunner()
    # When: the real Typer command is invoked
    result = runner.invoke(
        app,
        [
            "plan",
            "--source",
            "uf",
            "--year",
            "2024",
            "--dry-run",
            "--demo-estimated-bytes",
            str(1024**3),
        ],
    )
    parsed = BatchPlan.model_validate_json(result.stdout)
    # Then: automation receives a successful zero-write plan
    assert result.exit_code == 0
    assert parsed.cloud_writes == 0


def test_plan_command_returns_exit_three_when_cap_is_exceeded() -> None:
    # Given: a byte estimate one byte above the 25 GiB default
    runner = CliRunner()
    # When: the real planner is invoked
    result = runner.invoke(
        app,
        [
            "plan",
            "--source",
            "uf",
            "--year",
            "2024",
            "--demo-estimated-bytes",
            str(25 * 1024**3 + 1),
        ],
    )
    # Then: the stable cost exit is returned before writes
    assert result.exit_code == 3
    assert '"status":"cost_limit_exceeded"' in result.stderr


def test_source_inspect_and_local_execute_expose_real_subapp_surfaces(tmp_path: Path) -> None:
    # Given: the isolated CLI fixture adapter
    del tmp_path
    runner = CliRunner()
    # When: source inspection and local execution are invoked
    inspected = runner.invoke(app, ["source", "inspect", "--source", "uf", "--demo"])
    executed = runner.invoke(
        app,
        ["run", "--source", "uf", "--year", "2024", "--execute", "--demo"],
    )
    inspection = SourceInspection.model_validate_json(inspected.stdout)
    manifest = BatchManifest.model_validate_json(executed.stdout)
    # Then: both surfaces return typed results without cloud credentials
    assert inspected.exit_code == 0
    assert inspection.identity.location == "US"
    assert executed.exit_code == 0
    assert manifest.status.value == "completed"


def test_invalid_source_returns_exit_two_when_planned() -> None:
    # Given: an unknown source name
    runner = CliRunner()
    # When: it crosses the CLI boundary
    result = runner.invoke(app, ["plan", "--source", "injetar", "--year", "2024"])
    # Then: it is rejected as invalid configuration
    assert result.exit_code == 2
