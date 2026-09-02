from typing import override

import pytest
from google.api_core.exceptions import PreconditionFailed, ServiceUnavailable

from alfabetizacao_pipeline.batch.adapters import (
    GcsObjectStore,
    GcsObjectVersion,
    ImmutableCopy,
    ImmutableDownload,
    ImmutableUpload,
)
from alfabetizacao_pipeline.batch.google_adapters import RetryEvent
from alfabetizacao_pipeline.batch.google_storage import GoogleGcsSdk
from alfabetizacao_pipeline.batch.google_storage_native import (
    StorageCopyRequest,
    StoredBlob,
    StoredVersion,
)


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[RetryEvent] = []

    def retrying(self, event: RetryEvent) -> None:
        self.events.append(event)


class FlakyStorageClient:
    def __init__(self) -> None:
        self.upload_calls: int = 0
        self.copy_calls: int = 0

    def stat(self, bucket: str, name: str) -> StoredVersion:
        del bucket
        return StoredVersion(name, 7, 2)

    def download(
        self,
        bucket: str,
        name: str,
        generation: int,
        metageneration: int,
    ) -> bytes:
        del generation, metageneration
        return f"{bucket}/{name}".encode()

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        del bucket, name
        self.upload_calls += 1
        if self.upload_calls == 1:
            message = "transient"
            raise ServiceUnavailable(message)
        return StoredBlob(generation=7, crc32c="4waSgw==", size=len(payload))

    def copy_immutable(self, request: StorageCopyRequest) -> StoredBlob:
        del request
        self.copy_calls += 1
        return StoredBlob(generation=8, crc32c="4waSgw==", size=9)

    def list_versions(self, bucket: str, prefix: str) -> tuple[StoredVersion, ...]:
        del bucket
        return (StoredVersion(prefix + "part-00000.parquet", 7, 2),)


class LostCopyResponseClient(FlakyStorageClient):
    @override
    def stat(self, bucket: str, name: str) -> StoredVersion:
        del bucket
        generation = 7 if name.startswith("landing/") else 8
        return StoredVersion(name, generation, 2)

    @override
    def download(
        self,
        bucket: str,
        name: str,
        generation: int,
        metageneration: int,
    ) -> bytes:
        del bucket, name, generation, metageneration
        return b"same-exported-bytes"

    @override
    def copy_immutable(self, request: StorageCopyRequest) -> StoredBlob:
        del request
        message = "destination already created before response was lost"
        raise PreconditionFailed(message)


def test_google_storage_adapter_retries_and_returns_sdk_crc32c_metadata() -> None:
    client = FlakyStorageClient()
    observer = RecordingObserver()
    sdk = GoogleGcsSdk("project", client=client, observer=observer)
    result = sdk.upload(ImmutableUpload(uri="gs://bucket/object", payload=b"123456789"))
    assert (result.generation, result.crc32c, client.upload_calls) == (7, "4waSgw==", 2)
    assert tuple(event.operation for event in observer.events) == ("gcs.upload",)


def test_google_storage_copy_preserves_source_generation_and_destination_precondition() -> None:
    client = FlakyStorageClient()
    sdk = GoogleGcsSdk("project", client=client)

    result = sdk.copy(
        ImmutableCopy(
            source=GcsObjectVersion("gs://landing/part.parquet", 7, 2),
            destination_uri="gs://bronze/part.parquet",
        )
    )

    assert (result.uri, result.generation, client.copy_calls) == (
        "gs://bronze/part.parquet",
        8,
        1,
    )


def test_google_storage_copy_retry_reuses_identical_created_destination() -> None:
    store = GcsObjectStore(GoogleGcsSdk("project", client=LostCopyResponseClient()))
    landing = store.read_versioned("gs://bucket/landing/part.parquet")

    result = store.copy_immutable(landing.version, "gs://bucket/bronze/part.parquet")

    assert (result.generation, result.size_bytes) == (8, len(landing.payload))


def test_google_storage_rejects_non_gcs_uri() -> None:
    storage = GoogleGcsSdk("project", client=FlakyStorageClient())

    with pytest.raises(ValueError, match="https://bucket/object"):
        _ = storage.download(ImmutableDownload(GcsObjectVersion("https://bucket/object", 7, 2)))
