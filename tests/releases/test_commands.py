from pathlib import Path

from pydantic import TypeAdapter
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.releases.commands import app
from alfabetizacao_pipeline.releases.models import Release


def test_release_select_command_uses_typed_manifest_fixture(tmp_path: Path) -> None:
    # Given: one completed immutable manifest for every expected source
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
    # When: release selection is invoked through Typer
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
    # Then: exactly the six expected partitions are mapped
    assert result.exit_code == 0
    assert frozenset(partition.source for partition in release.partitions) == frozenset(
        SOURCE_CATALOG
    )


def test_release_select_command_reports_incomplete_release(tmp_path: Path) -> None:
    # Given: a fixture containing only one of the six required sources
    manifest = manifest_fixture(
        ManifestFixtureSpec("uf-2024", "uf", 2024, BatchStatus.COMPLETED, None)
    )
    completed = manifest.model_copy(update={"completed_at": manifest.started_at})
    fixture = tmp_path / "manifests.json"
    _ = fixture.write_bytes(TypeAdapter(tuple[BatchManifest, ...]).dump_json((completed,)))
    expected_source_options = [
        option for source in SOURCE_CATALOG for option in ("--expected-source", source)
    ]
    # When: the incomplete fixture crosses the real CLI boundary
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
    # Then: selection fails closed with its machine-readable status
    assert result.exit_code == 2
    assert '{"status":"incomplete_release"}' in result.stderr


def test_release_mutation_commands_are_dry_run_only_without_cloud_authorization() -> None:
    # Given: the release command surface
    runner = CliRunner()
    # When: both release command paths are invoked
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
    # Then: SQL is parameterized and cloud execution remains blocked
    assert dry_run.exit_code == 0
    assert "@candidate_release_id" in dry_run.stdout
    assert execute.exit_code == 5


def test_promotion_and_rollback_reject_missing_release_identifiers() -> None:
    # Given: blank promotion and missing rollback identifiers
    runner = CliRunner()
    # When: invalid identifiers cross the CLI boundary
    promotion = runner.invoke(
        app,
        ["promote", "--release-id", "", "--table", "project.ops.active_release"],
    )
    rollback = runner.invoke(
        app,
        ["rollback", "--active-release-id", "active", "--previous-release-id", ""],
    )
    # Then: neither command renders executable SQL
    assert promotion.exit_code == 2
    assert rollback.exit_code == 2
    assert "UPDATE" not in promotion.stdout
    assert "UPDATE" not in rollback.stdout
