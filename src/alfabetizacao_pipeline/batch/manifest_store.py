from datetime import UTC, datetime
from hashlib import sha256

from pydantic import ValidationError

from alfabetizacao_pipeline.batch.adapters import (
    GcsSdkBoundary,
    ImmutableDownload,
    ImmutableUpload,
)
from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    ManifestConflictError,
)
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus


class GcsManifestStore:
    """Immutable, generation-guarded manifest history stored in GCS."""

    def __init__(self, prefix: str, sdk: GcsSdkBoundary) -> None:
        """Bind a control prefix and the concrete storage boundary."""
        self._prefix: str = prefix.rstrip("/")
        self._sdk: GcsSdkBoundary = sdk

    def latest_completed(self, source: str, year: int) -> BatchManifest | None:
        """Resolve the newest valid completed checkpoint from persistent history."""
        prefix = f"{self._prefix}/{source}/ano={year}/"
        candidates: list[BatchManifest] = []
        for version in self._sdk.list(prefix):
            if not version.uri.endswith("/checkpoint=completed/manifest.json"):
                continue
            try:
                manifest = BatchManifest.model_validate_json(
                    self._sdk.download(ImmutableDownload(version))
                )
            except ValidationError:
                continue
            if (
                manifest.source == source
                and manifest.year == year
                and manifest.status is BatchStatus.COMPLETED
                and manifest.completed_at is not None
            ):
                candidates.append(manifest)
        return max(
            candidates,
            key=lambda item: item.completed_at or datetime.min.replace(tzinfo=UTC),
            default=None,
        )

    def persist(self, manifest: BatchManifest) -> None:
        """Create one immutable checkpoint or accept an identical retry."""
        uri = self._checkpoint_uri(manifest)
        payload = manifest.model_dump_json().encode("utf-8")
        try:
            _ = self._sdk.upload(ImmutableUpload(uri=uri, payload=payload))
        except ImmutableObjectExistsError as error:
            version = self._sdk.stat(uri)
            observed = self._sdk.download(ImmutableDownload(version))
            if sha256(observed).digest() != sha256(payload).digest():
                raise ManifestConflictError(uri=uri) from error

    def _checkpoint_uri(self, manifest: BatchManifest) -> str:
        return (
            f"{self._prefix}/{manifest.source}/ano={manifest.year}/run={manifest.run_id}/"
            f"checkpoint={manifest.status.value}/manifest.json"
        )
