from datetime import UTC, datetime

import pytest
from google.api_core.exceptions import PreconditionFailed

from alfabetizacao_pipeline.batch.adapters import (
    GcsObjectVersion,
    ImmutableCopy,
    ImmutableDownload,
    ImmutableUpload,
)
from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    StaleObjectGenerationError,
)
from alfabetizacao_pipeline.batch.fakes import ManifestFixtureSpec, manifest_fixture
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk
from alfabetizacao_pipeline.batch.google_storage_native import (
    StorageCopyRequest,
    StoredBlob,
    StoredVersion,
)
from alfabetizacao_pipeline.batch.manifest_store import GcsManifestStore
from alfabetizacao_pipeline.batch.models import BatchStatus, BronzeObject


class RacingManifestSdk:
    def __init__(self) -> None:
        self.uri: str = (
            "gs://control/manifests/uf/ano=2024/run=run/checkpoint=completed/manifest.json"
        )
        self.generation: int = 1
        self.metageneration: int = 1
        manifest = manifest_fixture(
            ManifestFixtureSpec(
                "run",
                "uf",
                2024,
                BatchStatus.COMPLETED,
                datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        self.payload: bytes = manifest.model_dump_json().encode()
        self.race_on_download: bool = False

    def stat(self, uri: str) -> GcsObjectVersion:
        return GcsObjectVersion(uri, self.generation, self.metageneration)

    def download(self, request: ImmutableDownload) -> bytes:
        if self.race_on_download:
            self.generation += 1
            self.metageneration += 1
            self.race_on_download = False
        if (
            request.version.generation != self.generation
            or request.version.metageneration != self.metageneration
        ):
            raise StaleObjectGenerationError(uri=request.version.uri)
        return self.payload

    def upload(self, request: ImmutableUpload) -> BronzeObject:
        del request
        raise ImmutableObjectExistsError(uri=self.uri)

    def copy(self, request: ImmutableCopy) -> BronzeObject:
        raise ImmutableObjectExistsError(uri=request.destination_uri)

    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        del prefix
        return (self.stat(self.uri),)


class StaleStorageClient:
    def stat(self, bucket: str, name: str) -> StoredVersion:
        del bucket
        return StoredVersion(name, 3, 2)

    def download(
        self,
        bucket: str,
        name: str,
        generation: int,
        metageneration: int,
    ) -> bytes:
        del bucket, name, generation, metageneration
        message = "stale"
        raise PreconditionFailed(message)

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        del bucket, name, payload
        raise AssertionError

    def copy_immutable(self, request: StorageCopyRequest) -> StoredBlob:
        del request
        raise AssertionError

    def list_versions(self, bucket: str, prefix: str) -> tuple[StoredVersion, ...]:
        del bucket, prefix
        return ()


def test_manifest_selection_fails_when_generation_changes_after_listing() -> None:
    sdk = RacingManifestSdk()
    sdk.race_on_download = True
    store = GcsManifestStore("gs://control/manifests", sdk)
    with pytest.raises(StaleObjectGenerationError):
        _ = store.latest_completed("uf", 2024)


def test_manifest_conflict_reread_is_pinned_to_observed_generation() -> None:
    sdk = RacingManifestSdk()
    sdk.race_on_download = True
    store = GcsManifestStore("gs://control/manifests", sdk)
    manifest = manifest_fixture(
        ManifestFixtureSpec(
            "run",
            "uf",
            2024,
            BatchStatus.COMPLETED,
            datetime(2025, 1, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(StaleObjectGenerationError):
        store.persist(manifest)


def test_google_adapter_maps_generation_precondition_failure() -> None:
    sdk = GoogleGcsSdk("project", client=StaleStorageClient())
    version = sdk.stat("gs://control/manifest.json")
    with pytest.raises(StaleObjectGenerationError):
        _ = sdk.download(ImmutableDownload(version))
