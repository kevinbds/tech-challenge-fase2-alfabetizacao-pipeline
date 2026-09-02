import pytest
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch import commands
from alfabetizacao_pipeline.batch.adapters import BigQueryAdapter
from alfabetizacao_pipeline.batch.google_bigquery import GoogleBigQuerySdk
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk
from alfabetizacao_pipeline.batch.manifest_store import GcsManifestStore
from alfabetizacao_pipeline.batch.production import (
    ProductionComposition,
    ProductionDependencies,
    build_production_composition,
)
from alfabetizacao_pipeline.config import AppSettings
from tests.batch.test_google_bigquery_adapter import RecordingBigQueryClient
from tests.batch.test_google_production_adapters import FlakyStorageClient


def production_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ProductionComposition, RecordingBigQueryClient]:
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())
    client = RecordingBigQueryClient()
    query_sdk = GoogleBigQuerySdk("project", storage, client=client)
    monkeypatch.setenv("ALFABETIZACAO_LANDING_PREFIX", "gs://bucket/landing/batch")
    monkeypatch.setenv("ALFABETIZACAO_BRONZE_PREFIX", "gs://bucket/bronze")
    monkeypatch.setenv("ALFABETIZACAO_MANIFEST_PREFIX", "gs://bucket/manifests")
    composition = build_production_composition(
        "uf",
        AppSettings(),
        git_sha="abc",
        image_digest="sha256:abc",
        dependencies=ProductionDependencies(storage=storage, query=query_sdk),
    )
    return composition, client


def test_production_composition_injects_cloud_ports_without_fixture_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition, _ = production_composition(monkeypatch)

    assert isinstance(composition.runtime.query, BigQueryAdapter)
    assert isinstance(composition.runtime.manifests, GcsManifestStore)


def test_run_dry_run_uses_injected_production_composition_without_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    composition, client = production_composition(monkeypatch)

    def factory(
        source: str,
        settings: AppSettings,
        *,
        git_sha: str,
        image_digest: str,
    ) -> ProductionComposition:
        del source, settings, git_sha, image_digest
        return composition

    monkeypatch.setattr(commands, "build_production_composition", factory)
    result = CliRunner().invoke(
        commands.app,
        ["run", "--source", "uf", "--year", "2024", "--dry-run"],
        env={
            "ALFABETIZACAO_GIT_SHA": "abc",
            "ALFABETIZACAO_IMAGE_DIGEST": "sha256:abc",
        },
    )
    assert result.exit_code == 0
    assert '"query_hash":"fixture-query-hash"' not in result.stdout
    assert tuple(dry_run for _, dry_run, _ in client.executions) == (True,)
