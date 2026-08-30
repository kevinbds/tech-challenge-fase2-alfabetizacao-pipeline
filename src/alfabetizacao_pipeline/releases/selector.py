from datetime import datetime

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.releases.models import Release, ReleasePartition


def select_latest_completed(
    manifests: tuple[BatchManifest, ...],
    release_id: str,
    created_at: datetime,
    *,
    expected_keys: frozenset[tuple[str, int]],
) -> Release:
    """Require exactly one completed manifest for every explicit expected key."""
    expected_years = frozenset(year for _, year in expected_keys)
    required_keys = frozenset(
        (source, year) for year in expected_years for source in SOURCE_CATALOG
    )
    if not expected_keys or not required_keys.issubset(expected_keys):
        raise IncompleteRunError(run_id="release-expected-set-incomplete")
    selected: dict[tuple[str, int], BatchManifest] = {}
    for manifest in manifests:
        key = (manifest.source, manifest.year)
        if (
            key not in expected_keys
            or key in selected
            or manifest.status is not BatchStatus.COMPLETED
            or manifest.completed_at is None
        ):
            raise IncompleteRunError(run_id=manifest.run_id)
        selected[key] = manifest
    if frozenset(selected) != expected_keys:
        raise IncompleteRunError(run_id="release-partition-set-mismatch")
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
