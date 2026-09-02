from dataclasses import dataclass
from typing import Protocol, TypedDict, Unpack, runtime_checkable

from google.cloud import storage


@dataclass(frozen=True, slots=True)
class StoredBlob:
    """Metadata returned only after an immutable GCS write succeeds."""

    generation: int
    crc32c: str
    size: int


@dataclass(frozen=True, slots=True)
class StoredVersion:
    """Generation pair required to make a GCS read immutable."""

    name: str
    generation: int
    metageneration: int


@dataclass(frozen=True, slots=True)
class StorageCopyRequest:
    """Source generation and create-only destination for a server-side copy."""

    source_bucket: str
    source_name: str
    source_generation: int
    destination_bucket: str
    destination_name: str


class StorageClientBoundary(Protocol):
    """Typed subset of GCS operations used by the batch adapters."""

    def stat(self, bucket: str, name: str) -> StoredVersion:
        """Return the current generation pair for an object."""
        ...

    def download(
        self,
        bucket: str,
        name: str,
        generation: int,
        metageneration: int,
    ) -> bytes:
        """Read bytes only when both selected generations still match."""
        ...

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        """Create an object with the generation-zero precondition."""
        ...

    def copy_immutable(self, request: StorageCopyRequest) -> StoredBlob:
        """Copy one selected source generation into an absent destination."""
        ...

    def list_versions(self, bucket: str, prefix: str) -> tuple[StoredVersion, ...]:
        """List immutable version metadata below a control prefix."""
        ...


class _CopyOptions(TypedDict):
    new_name: str
    source_generation: int
    if_source_generation_match: int
    if_generation_match: int
    retry: None


@runtime_checkable
class _CopyingBucket(Protocol):
    def blob(self, blob_name: str, *, generation: int | None = None) -> storage.Blob: ...

    def copy_blob(
        self,
        blob: storage.Blob,
        destination_bucket: storage.Bucket,
        **options: Unpack[_CopyOptions],
    ) -> storage.Blob: ...


class NativeStorageClient:
    """Google SDK facade that enforces immutable reads and writes."""

    def __init__(self, project: str) -> None:
        """Create the authenticated client for the destination project."""
        self._client: storage.Client = storage.Client(project=project)

    def stat(self, bucket: str, name: str) -> StoredVersion:
        """Reload metadata before selecting an immutable object version."""
        blob = self._client.bucket(bucket).blob(name)
        blob.reload()
        return _stored_version(bucket, blob)

    def download(
        self,
        bucket: str,
        name: str,
        generation: int,
        metageneration: int,
    ) -> bytes:
        """Download with checksum and generation preconditions enabled."""
        return (
            self._client.bucket(bucket)
            .blob(name, generation=generation)
            .download_as_bytes(
                checksum="crc32c",
                if_generation_match=generation,
                if_metageneration_match=metageneration,
            )
        )

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        """Upload only when no generation exists at the destination."""
        blob = self._client.bucket(bucket).blob(name)
        blob.upload_from_string(
            payload,
            if_generation_match=0,
            checksum="crc32c",
            retry=None,
        )
        blob.reload()
        if blob.generation is None or blob.crc32c is None or blob.size is None:
            message = f"missing-object-metadata:{bucket}/{name}"
            raise ValueError(message)
        return StoredBlob(
            generation=int(blob.generation),
            crc32c=blob.crc32c,
            size=int(blob.size),
        )

    def copy_immutable(self, request: StorageCopyRequest) -> StoredBlob:
        """Copy only the selected source generation into an absent destination."""
        source_bucket = self._client.bucket(request.source_bucket)
        if not isinstance(source_bucket, _CopyingBucket):
            message = f"unsupported-storage-client:{type(source_bucket).__name__}"
            raise TypeError(message)
        destination_bucket = self._client.bucket(request.destination_bucket)
        source = source_bucket.blob(
            request.source_name,
            generation=request.source_generation,
        )
        copied = source_bucket.copy_blob(
            source,
            destination_bucket,
            new_name=request.destination_name,
            source_generation=request.source_generation,
            if_source_generation_match=request.source_generation,
            if_generation_match=0,
            retry=None,
        )
        copied.reload()
        if copied.generation is None or copied.crc32c is None or copied.size is None:
            message = (
                f"missing-object-metadata:{request.destination_bucket}/{request.destination_name}"
            )
            raise ValueError(message)
        return StoredBlob(
            generation=int(copied.generation),
            crc32c=copied.crc32c,
            size=int(copied.size),
        )

    def list_versions(self, bucket: str, prefix: str) -> tuple[StoredVersion, ...]:
        """Return stable object versions in lexical name order."""
        return tuple(
            sorted(
                (
                    _stored_version(bucket, blob)
                    for blob in self._client.list_blobs(bucket, prefix=prefix)
                ),
                key=lambda version: version.name,
            )
        )


def _stored_version(bucket: str, blob: storage.Blob) -> StoredVersion:
    if blob.generation is None or blob.metageneration is None:
        message = f"missing-object-version:{bucket}/{blob.name}"
        raise ValueError(message)
    return StoredVersion(blob.name, int(blob.generation), int(blob.metageneration))
