from datetime import UTC, datetime

from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BatchStatus,
    BronzeObject,
    SourceIdentity,
)
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution


def release_execution() -> ReleaseExecution:
    return ReleaseExecution(
        release_id="batch-202608-y2024-r0123456789ab",
        year=2024,
    )


def completed_manifest(
    source: str,
    *,
    generation: int = 1,
    row_count: int = 10,
    verified_at: datetime | None = None,
) -> BatchManifest:
    return BatchManifest(
        run_id=f"run-{source}",
        source=source,
        year=2024,
        status=BatchStatus.COMPLETED,
        source_identity=SourceIdentity(location="US", etag="fixture"),
        row_count=row_count,
        fingerprint=f"fingerprint-{source}",
        query_hash="query",
        schema_hash="schema",
        bronze_objects=(
            BronzeObject(
                uri=f"gs://bronze/bronze/{source}/ano=2024/run=run-{source}/part-00000.parquet",
                generation=generation,
                crc32c=f"crc-{source}",
                size_bytes=100,
            ),
        ),
        started_at=datetime(2026, 8, 30, tzinfo=UTC),
        completed_at=datetime(2026, 8, 30, 0, 1, tzinfo=UTC),
        verified_at=verified_at or datetime(2026, 8, 30, 0, 1, tzinfo=UTC),
        git_sha="abc",
        image_digest="sha256:abc",
    )
