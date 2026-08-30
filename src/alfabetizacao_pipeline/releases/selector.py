from datetime import datetime

from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.releases.models import Release, ReleasePartition


def select_latest_completed(
    manifests: tuple[BatchManifest, ...],
    release_id: str,
    created_at: datetime,
) -> Release:
    """Select only the newest completed run for each source and year."""
    selected: dict[tuple[str, int], BatchManifest] = {}
    for manifest in manifests:
        if manifest.status is not BatchStatus.COMPLETED or manifest.completed_at is None:
            continue
        key = (manifest.source, manifest.year)
        existing = selected.get(key)
        if existing is None or _completed_at(manifest) > _completed_at(existing):
            selected[key] = manifest
    partitions = tuple(
        ReleasePartition(
            source=source,
            year=year,
            run_id=manifest.run_id,
            manifest_uri=f"gs://manifests/{source}/ano={year}/run={manifest.run_id}/manifest.json",
        )
        for (source, year), manifest in sorted(selected.items())
    )
    return Release(release_id=release_id, created_at=created_at, partitions=partitions)


def _completed_at(manifest: BatchManifest) -> datetime:
    completed_at = manifest.completed_at
    if completed_at is None:
        raise IncompleteRunError(run_id=manifest.run_id)
    return completed_at
