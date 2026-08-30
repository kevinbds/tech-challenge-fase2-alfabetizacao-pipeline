from pathlib import Path

from pydantic import TypeAdapter
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.releases.commands import app
from alfabetizacao_pipeline.releases.models import Release


def test_release_select_command_uses_typed_manifest_fixture(tmp_path: Path) -> None:
    # Given: one completed and one failed immutable manifest
    manifests = (
        manifest_fixture(ManifestFixtureSpec("ok", "uf", 2024, BatchStatus.COMPLETED, None)),
        manifest_fixture(ManifestFixtureSpec("failed", "uf", 2024, BatchStatus.FAILED, None)),
    )
    completed = manifests[0].model_copy(update={"completed_at": manifests[0].started_at})
    fixture = tmp_path / "manifests.json"
    _ = fixture.write_bytes(
        TypeAdapter(tuple[BatchManifest, ...]).dump_json((completed, manifests[1]))
    )
    # When: release selection is invoked through Typer
    result = CliRunner().invoke(
        app,
        ["select", "--manifests", str(fixture), "--release-id", "release-1"],
    )
    release = Release.model_validate_json(result.stdout)
    # Then: only the completed run is mapped
    assert result.exit_code == 0
    assert tuple(partition.run_id for partition in release.partitions) == ("ok",)


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
