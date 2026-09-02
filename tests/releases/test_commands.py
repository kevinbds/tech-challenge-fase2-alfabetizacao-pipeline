from pathlib import Path

import pytest
from pydantic import TypeAdapter
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.cli import app as root_app
from alfabetizacao_pipeline.releases.commands import app
from alfabetizacao_pipeline.releases.models import Release


def test_release_select_command_uses_typed_manifest_fixture(tmp_path: Path) -> None:
    manifests = tuple(
        manifest_fixture(
            ManifestFixtureSpec(
                f"{source}-2024",
                source,
                2024,
                BatchStatus.COMPLETED,
                None,
            )
        )
        for source in SOURCE_CATALOG
    )
    completed = tuple(
        manifest.model_copy(update={"completed_at": manifest.started_at}) for manifest in manifests
    )
    fixture = tmp_path / "manifests.json"
    _ = fixture.write_bytes(TypeAdapter(tuple[BatchManifest, ...]).dump_json(completed))
    expected_source_options = [
        option for source in SOURCE_CATALOG for option in ("--expected-source", source)
    ]
    result = CliRunner().invoke(
        app,
        [
            "select",
            "--manifests",
            str(fixture),
            "--release-id",
            "release-1",
            "--year",
            "2024",
            *expected_source_options,
        ],
    )
    release = Release.model_validate_json(result.stdout)
    assert result.exit_code == 0
    assert frozenset(partition.source for partition in release.partitions) == frozenset(
        SOURCE_CATALOG
    )


def test_release_select_command_reports_incomplete_release(tmp_path: Path) -> None:
    manifest = manifest_fixture(
        ManifestFixtureSpec("uf-2024", "uf", 2024, BatchStatus.COMPLETED, None)
    )
    completed = manifest.model_copy(update={"completed_at": manifest.started_at})
    fixture = tmp_path / "manifests.json"
    _ = fixture.write_bytes(TypeAdapter(tuple[BatchManifest, ...]).dump_json((completed,)))
    expected_source_options = [
        option for source in SOURCE_CATALOG for option in ("--expected-source", source)
    ]
    result = CliRunner().invoke(
        app,
        [
            "select",
            "--manifests",
            str(fixture),
            "--release-id",
            "release-incomplete",
            "--year",
            "2024",
            *expected_source_options,
        ],
    )
    assert result.exit_code == 2
    assert '{"status":"incomplete_release"}' in result.stderr


def test_release_mutation_commands_are_dry_run_only_without_cloud_authorization() -> None:
    runner = CliRunner()
    dry_run = runner.invoke(
        app,
        ["promote", "--release-id", "candidate", "--table", "project.ops.active_release"],
    )
    execute = runner.invoke(
        app,
        [
            "promote",
            "--release-id",
            "candidate",
            "--table",
            "project.ops.active_release",
            "--execute",
        ],
    )
    assert dry_run.exit_code == 0
    assert "@release_id" in dry_run.stdout
    assert execute.exit_code == 5


@pytest.mark.parametrize(
    "arguments",
    [
        ("promote", "--release-id", "candidate", "--table", "demo_project.ops.active_release"),
        ("rollback", "--reference-year", "2024", "--table", "demo_project.ops.active_release"),
    ],
)
def test_release_mutation_commands_report_invalid_table_identifier(
    arguments: tuple[str, ...],
) -> None:
    result = CliRunner().invoke(app, list(arguments))

    assert result.exit_code == 2
    assert result.stderr == '{"status":"invalid_table_identifier"}\n'
    assert "FrozenInstanceError" not in result.output


def test_promotion_rejects_a_missing_release_identifier() -> None:
    runner = CliRunner()
    promotion = runner.invoke(
        app,
        ["promote", "--release-id", "", "--table", "project.ops.active_release"],
    )
    assert promotion.exit_code == 2
    assert "UPDATE" not in promotion.stdout


def test_release_alias_renders_historical_rollback_sql_for_a_reference_year() -> None:
    result = CliRunner().invoke(
        root_app,
        [
            "release",
            "rollback",
            "--reference-year",
            "2024",
            "--table",
            "project.ops.active_release",
        ],
    )
    assert result.exit_code == 0
    assert "declare target_year int64 default 2024;" in result.stdout
    assert "release_id" in result.stdout
    assert "prior_release_id" in result.stdout
    assert "active_release_id" not in result.stdout
    assert "previous_release_id" not in result.stdout


def test_rollback_keeps_cloud_execution_blocked_after_year_validation() -> None:
    result = CliRunner().invoke(
        app,
        [
            "rollback",
            "--reference-year",
            "2024",
            "--table",
            "project.ops.active_release",
            "--execute",
        ],
    )
    assert result.exit_code == 5


def test_rollback_rejects_an_invalid_reference_year() -> None:
    result = CliRunner().invoke(
        app,
        ["rollback", "--reference-year", "2101", "--table", "project.ops.active_release"],
    )
    assert result.exit_code == 2
    assert "UPDATE" not in result.stdout
