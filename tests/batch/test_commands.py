from pathlib import Path

import pytest
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch import commands
from alfabetizacao_pipeline.batch.commands import app
from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import (
    BatchEstimate,
    BatchManifest,
    BatchRunContext,
    DryRunEstimate,
    SourceInspection,
)
from alfabetizacao_pipeline.batch.production import ProductionComposition
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution
from alfabetizacao_pipeline.batch.release_store import InMemoryReleaseStore
from alfabetizacao_pipeline.batch.runtime import BatchRuntime, SystemClock
from alfabetizacao_pipeline.config import AppSettings
from tests.batch.parquet_fixtures import parquet_payload


def test_plan_command_returns_json_and_zero_writes_when_dry_run() -> None:
    runner = CliRunner()
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
    parsed = BatchEstimate.model_validate_json(result.stdout)
    assert result.exit_code == 0
    assert parsed.cloud_writes == 0


@pytest.mark.parametrize(
    "arguments",
    [
        ("plan", "--demo-estimated-bytes", "1024"),
        ("run", "--demo"),
    ],
)
def test_dry_run_commands_use_estimate_without_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
) -> None:
    query = FakeBigQuery(estimate=DryRunEstimate(bytes_processed=1024))

    def demo_query(estimated_bytes: int, *, snapshot_row_count: int = 0) -> FakeBigQuery:
        del estimated_bytes, snapshot_row_count
        return query

    monkeypatch.setattr(commands, "_query", demo_query)
    result = CliRunner().invoke(app, [*arguments, "--source", "uf", "--year", "2024", "--dry-run"])
    parsed = BatchEstimate.model_validate_json(result.stdout)
    assert result.exit_code == 0
    assert parsed.estimated_bytes == 1024
    assert query.executed_queries == 0


def test_plan_command_returns_exit_three_when_cap_is_exceeded() -> None:
    runner = CliRunner()
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
    assert result.exit_code == 3
    assert '"status":"cost_limit_exceeded"' in result.stderr


def test_plan_command_rejects_execute_alias_before_query_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_constructed = False

    def unexpected_query(_source: str, _settings: AppSettings) -> FakeBigQuery:
        nonlocal query_constructed
        query_constructed = True
        return FakeBigQuery(estimate=DryRunEstimate(bytes_processed=1))

    monkeypatch.setattr(commands, "build_production_query", unexpected_query)
    result = CliRunner().invoke(
        app,
        ["plan", "--source", "uf", "--year", "2024", "--execute"],
    )

    assert result.exit_code == 2
    assert "No such option: --execute" in result.output
    assert query_constructed is False


def test_plan_command_returns_stable_json_when_demo_estimate_is_negative() -> None:
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "--source",
            "uf",
            "--year",
            "2024",
            "--demo-estimated-bytes",
            "-1",
        ],
    )

    assert result.exit_code == 2
    assert result.stderr == '{"status":"invalid_request"}\n'
    assert "ValidationError" not in result.output


def test_plan_command_rejects_limit_above_configured_cap() -> None:
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "--source",
            "uf",
            "--year",
            "2024",
            "--maximum-bytes-billed",
            "8",
        ],
        env={"ALFABETIZACAO_MAX_BYTES_BILLED": "7"},
    )
    assert result.exit_code == 2


def test_production_run_propagates_environment_cap_to_all_query_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    landing = tmp_path / "landing.parquet"
    _ = landing.write_bytes(parquet_payload("uf", (1,)))
    query = FakeBigQuery(DryRunEstimate(bytes_processed=1), snapshot_row_count=1)
    objects = InMemoryObjectStore()
    objects.seed("gs://landing/fixture.parquet", landing.read_bytes())
    composition = ProductionComposition(
        runtime=BatchRuntime(
            query=query,
            manifests=InMemoryManifestStore(),
            objects=objects,
            clock=SystemClock(),
        ),
        context=BatchRunContext(
            landing_prefix="gs://landing",
            bronze_prefix="gs://bronze",
            git_sha="abc",
            image_digest="sha256:abc",
        ),
    )

    def factory(
        source: str,
        settings: AppSettings,
        *,
        git_sha: str,
        image_digest: str,
    ) -> ProductionComposition:
        del source, git_sha, image_digest
        assert settings.max_bytes_billed == 7
        return composition

    monkeypatch.setattr(commands, "build_production_composition", factory)
    release_store = InMemoryReleaseStore()
    release_store.begin(
        ReleaseExecution(
            release_id="batch-202608-y2024-r0123456789ab",
            year=2024,
        )
    )

    def release_store_factory(_settings: AppSettings) -> InMemoryReleaseStore:
        return release_store

    monkeypatch.setattr(commands, "_release_store", release_store_factory)
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--source",
            "uf",
            "--year",
            "2024",
            "--execute",
            "--release-id",
            "batch-202608-y2024-r0123456789ab",
        ],
        env={
            "ALFABETIZACAO_GIT_SHA": "abc",
            "ALFABETIZACAO_IMAGE_DIGEST": "sha256:abc",
            "ALFABETIZACAO_MAX_BYTES_BILLED": "7",
        },
    )
    assert result.exit_code == 0
    assert query.dry_run_limits == [7]
    assert query.export_limits == [7]


def test_source_inspect_and_local_execute_expose_real_subapp_surfaces(tmp_path: Path) -> None:
    del tmp_path
    runner = CliRunner()
    inspected = runner.invoke(app, ["source", "inspect", "--source", "uf", "--demo"])
    executed = runner.invoke(
        app,
        ["run", "--source", "uf", "--year", "2024", "--execute", "--demo"],
    )
    inspection = SourceInspection.model_validate_json(inspected.stdout)
    manifest = BatchManifest.model_validate_json(executed.stdout)
    assert inspected.exit_code == 0
    assert inspection.identity.location == "US"
    assert executed.exit_code == 0
    assert manifest.status.value == "completed"


def test_invalid_source_returns_exit_two_when_planned() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["plan", "--source", "injetar", "--year", "2024"])
    assert result.exit_code == 2
