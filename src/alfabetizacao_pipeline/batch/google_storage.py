from dataclasses import dataclass
from typing import Protocol, override
from urllib.parse import urlsplit

from google.api_core.exceptions import (
    InternalServerError,
    PreconditionFailed,
    ServiceUnavailable,
    TooManyRequests,
)
from google.cloud import storage

from alfabetizacao_pipeline.batch.adapters import GcsSdkBoundary, ImmutableUpload
from alfabetizacao_pipeline.batch.errors import ImmutableObjectExistsError
from alfabetizacao_pipeline.batch.google_adapters import RetryObserver, retry_call
from alfabetizacao_pipeline.batch.models import BronzeObject

RETRYABLE_STORAGE_ERRORS = (ServiceUnavailable, TooManyRequests, InternalServerError)


@dataclass(frozen=True, slots=True)
class StoredBlob:
    """Normalized immutable GCS object metadata."""

    generation: int
    crc32c: str
    size: int


class StorageClientBoundary(Protocol):
    """Narrow testable facade around google-cloud-storage."""

    def download(self, bucket: str, name: str) -> bytes:
        """Read one named object."""
        ...

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        """Create one object with generation-match zero."""
        ...

    def list_names(self, bucket: str, prefix: str) -> tuple[str, ...]:
        """List stable object names in lexical order."""
        ...


class NativeStorageClient:
    """Concrete google-cloud-storage facade."""

    def __init__(self, project: str) -> None:
        """Create an authenticated destination-project client."""
        self._client: storage.Client = storage.Client(project=project)

    def download(self, bucket: str, name: str) -> bytes:
        """Download bytes with the SDK checksum verification enabled."""
        return self._client.bucket(bucket).blob(name).download_as_bytes(checksum="crc32c")

    def upload_immutable(self, bucket: str, name: str, payload: bytes) -> StoredBlob:
        """Upload with a zero-generation precondition and CRC32C verification."""
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

    def list_names(self, bucket: str, prefix: str) -> tuple[str, ...]:
        """List object names without relying on a fixed location."""
        return tuple(sorted(blob.name for blob in self._client.list_blobs(bucket, prefix=prefix)))


class GoogleGcsSdk(GcsSdkBoundary):
    """Production GCS adapter with immutable writes and bounded retries."""

    def __init__(
        self,
        project: str,
        *,
        client: StorageClientBoundary | None = None,
        observer: RetryObserver | None = None,
        maximum_attempts: int = 3,
    ) -> None:
        """Bind the authenticated client and observable retry policy."""
        self._client: StorageClientBoundary = client or NativeStorageClient(project)
        self._observer: RetryObserver | None = observer
        self._maximum_attempts: int = maximum_attempts

    @override
    def download(self, uri: str) -> bytes:
        """Download one object using bounded retries."""
        bucket, name = _split_gs_uri(uri)
        return retry_call(
            "gcs.download",
            lambda: self._client.download(bucket, name),
            retryable=RETRYABLE_STORAGE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )

    @override
    def upload(self, request: ImmutableUpload) -> BronzeObject:
        """Create an immutable object or surface the generation conflict."""
        bucket, name = _split_gs_uri(request.uri)
        try:
            blob = retry_call(
                "gcs.upload",
                lambda: self._client.upload_immutable(bucket, name, request.payload),
                retryable=RETRYABLE_STORAGE_ERRORS,
                maximum_attempts=self._maximum_attempts,
                observer=self._observer,
            )
        except PreconditionFailed as error:
            raise ImmutableObjectExistsError(uri=request.uri) from error
        return BronzeObject(
            uri=request.uri,
            generation=blob.generation,
            crc32c=blob.crc32c,
            size_bytes=blob.size,
        )

    @override
    def list(self, prefix: str) -> tuple[str, ...]:
        """List exact gs:// URIs under a prefix using bounded retries."""
        bucket, name_prefix = _split_gs_uri(prefix)
        names = retry_call(
            "gcs.list",
            lambda: self._client.list_names(bucket, name_prefix),
            retryable=RETRYABLE_STORAGE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )
        return tuple(f"gs://{bucket}/{name}" for name in names)


def _split_gs_uri(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(uri)
    return parsed.netloc, parsed.path.lstrip("/")
