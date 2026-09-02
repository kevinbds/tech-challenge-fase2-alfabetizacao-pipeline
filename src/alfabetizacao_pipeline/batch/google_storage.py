from typing import override
from urllib.parse import urlsplit

from google.api_core.exceptions import (
    InternalServerError,
    NotFound,
    PreconditionFailed,
    ServiceUnavailable,
    TooManyRequests,
)

from alfabetizacao_pipeline.batch.adapters import (
    GcsObjectVersion,
    GcsSdkBoundary,
    ImmutableCopy,
    ImmutableDownload,
    ImmutableUpload,
)
from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    StaleObjectGenerationError,
)
from alfabetizacao_pipeline.batch.google_adapters import RetryObserver, retry_call
from alfabetizacao_pipeline.batch.google_storage_native import (
    NativeStorageClient,
    StorageClientBoundary,
    StorageCopyRequest,
)
from alfabetizacao_pipeline.batch.models import BronzeObject

RETRYABLE_STORAGE_ERRORS = (ServiceUnavailable, TooManyRequests, InternalServerError)


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
    def stat(self, uri: str) -> GcsObjectVersion:
        """Resolve exact generation metadata using bounded retries."""
        bucket, name = _split_gs_uri(uri)
        version = retry_call(
            "gcs.stat",
            lambda: self._client.stat(bucket, name),
            retryable=RETRYABLE_STORAGE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )
        return GcsObjectVersion(uri, version.generation, version.metageneration)

    @override
    def download(self, request: ImmutableDownload) -> bytes:
        """Download one object using bounded retries."""
        bucket, name = _split_gs_uri(request.version.uri)
        try:
            return retry_call(
                "gcs.download",
                lambda: self._client.download(
                    bucket,
                    name,
                    request.version.generation,
                    request.version.metageneration,
                ),
                retryable=RETRYABLE_STORAGE_ERRORS,
                maximum_attempts=self._maximum_attempts,
                observer=self._observer,
            )
        except PreconditionFailed as error:
            raise StaleObjectGenerationError(uri=request.version.uri) from error

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
    def copy(self, request: ImmutableCopy) -> BronzeObject:
        """Copy server-side and classify source staleness separately from conflicts."""
        source_bucket, source_name = _split_gs_uri(request.source.uri)
        destination_bucket, destination_name = _split_gs_uri(request.destination_uri)
        copy_request = StorageCopyRequest(
            source_bucket=source_bucket,
            source_name=source_name,
            source_generation=request.source.generation,
            destination_bucket=destination_bucket,
            destination_name=destination_name,
        )
        try:
            blob = retry_call(
                "gcs.copy",
                lambda: self._client.copy_immutable(copy_request),
                retryable=RETRYABLE_STORAGE_ERRORS,
                maximum_attempts=self._maximum_attempts,
                observer=self._observer,
            )
        except PreconditionFailed as error:
            try:
                current = self.stat(request.source.uri)
            except NotFound as missing:
                raise StaleObjectGenerationError(uri=request.source.uri) from missing
            if current.generation != request.source.generation:
                raise StaleObjectGenerationError(uri=request.source.uri) from error
            raise ImmutableObjectExistsError(uri=request.destination_uri) from error
        return BronzeObject(
            uri=request.destination_uri,
            generation=blob.generation,
            crc32c=blob.crc32c,
            size_bytes=blob.size,
        )

    @override
    def list(self, prefix: str) -> tuple[GcsObjectVersion, ...]:
        """List exact gs:// URIs under a prefix using bounded retries."""
        bucket, name_prefix = _split_gs_uri(prefix)
        versions = retry_call(
            "gcs.list",
            lambda: self._client.list_versions(bucket, name_prefix),
            retryable=RETRYABLE_STORAGE_ERRORS,
            maximum_attempts=self._maximum_attempts,
            observer=self._observer,
        )
        return tuple(
            GcsObjectVersion(
                f"gs://{bucket}/{version.name}",
                version.generation,
                version.metageneration,
            )
            for version in versions
        )


def _split_gs_uri(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(uri)
    return parsed.netloc, parsed.path.lstrip("/")
