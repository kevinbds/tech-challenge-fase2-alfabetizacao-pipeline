import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch import commands
from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchRunContext, BatchStatus
from alfabetizacao_pipeline.batch.production import ProductionComposition
from alfabetizacao_pipeline.config import AppSettings
from alfabetizacao_pipeline.releases.commands import app as release_app
from alfabetizacao_pipeline.releases.selector import select_latest_completed


def _completed(source: str, run_id: str = "run") -> BatchManifest:
    return manifest_fixture(
        ManifestFixtureSpec(
            run_id,
            source,
            2024,
            BatchStatus.COMPLETED,
            datetime(2025, 1, 1, tzinfo=UTC),
        )
    )


def _expected() -> frozenset[tuple[str, int]]:
    return frozenset((source, 2024) for source in SOURCE_CATALOG)


@pytest.mark.parametrize(
    "manifests",
    [
        (_completed("uf"),),
        (*(_completed(source) for source in SOURCE_CATALOG), _completed("uf", "duplicate")),
        (
            *(_completed(source) for source in SOURCE_CATALOG),
            manifest_fixture(
                ManifestFixtureSpec(
                    "failed",
                    "uf",
                    2024,
                    BatchStatus.FAILED,
                    datetime(2025, 1, 2, tzinfo=UTC),
                )
            ),
        ),
        (*(_completed(source) for source in SOURCE_CATALOG), _completed("extra")),
    ],
)
def test_release_rejects_missing_duplicate_failed_and_extra_partitions(
    manifests: tuple[BatchManifest, ...],
) -> None:
    with pytest.raises(IncompleteRunError):
        _ = select_latest_completed(
            manifests,
            "release",
            datetime(2025, 2, 1, tzinfo=UTC),
            expected_keys=_expected(),
        )


def test_release_accepts_exactly_one_completed_manifest_per_expected_key() -> None:
    manifests = tuple(_completed(source) for source in SOURCE_CATALOG)
    release = select_latest_completed(
        manifests,
        "release",
        datetime(2025, 2, 1, tzinfo=UTC),
        expected_keys=_expected(),
    )
    assert {(partition.source, partition.year) for partition in release.partitions} == _expected()


@pytest.mark.parametrize(
    ("git_sha", "image_digest"), [("", "sha256:x"), (" ", "sha256:x"), ("x", "")]
)
def test_batch_context_rejects_blank_deployment_provenance(
    git_sha: str,
    image_digest: str,
) -> None:
    with pytest.raises(ValidationError):
        _ = BatchRunContext(
            landing_prefix="gs://landing",
            bronze_prefix="gs://bronze",
            git_sha=git_sha,
            image_digest=image_digest,
        )


def test_batch_context_trims_deployment_provenance() -> None:
    context = BatchRunContext(
        landing_prefix="gs://landing",
        bronze_prefix="gs://bronze",
        git_sha=" abc ",
        image_digest=" sha256:x ",
    )
    assert (context.git_sha, context.image_digest) == ("abc", "sha256:x")


@pytest.mark.parametrize(
    "environment",
    [
        {"ALFABETIZACAO_IMAGE_DIGEST": "sha256:x"},
        {"ALFABETIZACAO_GIT_SHA": "x"},
        {"ALFABETIZACAO_GIT_SHA": "", "ALFABETIZACAO_IMAGE_DIGEST": "sha256:x"},
        {"ALFABETIZACAO_GIT_SHA": " ", "ALFABETIZACAO_IMAGE_DIGEST": "sha256:x"},
    ],
)
def test_production_cli_rejects_invalid_provenance_before_sdk_composition(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
) -> None:
    composed = False

    def trap(
        _source: str,
        _settings: AppSettings,
        *,
        git_sha: str,
        image_digest: str,
    ) -> ProductionComposition:
        nonlocal composed
        composed = True
        raise AssertionError((git_sha, image_digest))

    monkeypatch.setattr(commands, "build_production_composition", trap)
    result = CliRunner().invoke(
        commands.app,
        ["run", "--source", "uf", "--year", "2024", "--execute"],
        env=environment,
    )
    assert result.exit_code == 2
    assert result.stderr == '{"status":"invalid_deployment_provenance"}\n'
    assert composed is False


def test_release_cli_requires_explicit_expected_sources(tmp_path: Path) -> None:
    fixture = tmp_path / "manifests.json"
    _ = fixture.write_text("[" + _completed("uf").model_dump_json() + "]", encoding="utf-8")
    result = CliRunner().invoke(
        release_app,
        ["select", "--manifests", str(fixture), "--release-id", "release"],
    )
    assert result.exit_code == 2


def test_root_sqlfluff_uses_offline_jinja_templater() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["sqlfluff"]["core"]["templater"] == "jinja"


def test_plan_accepts_explicit_json_output_format() -> None:
    result = CliRunner().invoke(
        commands.app,
        [
            "plan",
            "--source",
            "uf",
            "--year",
            "2024",
            "--dry-run",
            "--format",
            "json",
            "--demo-estimated-bytes",
            "1024",
        ],
    )
    assert result.exit_code == 0
    assert '"estimated_bytes":1024' in result.stdout
