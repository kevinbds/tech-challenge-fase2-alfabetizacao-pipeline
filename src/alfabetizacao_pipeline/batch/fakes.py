from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import (
    ImmutableObjectExistsError,
    StaleObjectGenerationError,
)
from alfabetizacao_pipeline.batch.integrity import crc32c_base64
from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BatchStatus,
    BronzeObject,
    DryRunEstimate,
    ObjectVersion,
    QueryParameter,
    SnapshotExport,
    SourceIdentity,
    SourceInspection,
    VersionedPayload,
)


class FakeBigQuery:
    """Deterministic BigQuery port with observable export count."""

    def __init__(
        self,
        estimate: DryRunEstimate,
        *,
        snapshot_row_count: int = 0,
        snapshot_uris: tuple[str, ...] = ("gs://landing/fixture.parquet",),
    ) -> None:
        """Configure deterministic dry-run and snapshot responses."""
        self.estimate: DryRunEstimate = estimate
        self.snapshot_row_count: int = snapshot_row_count
        self.snapshot_uris: tuple[str, ...] = snapshot_uris
        self.query_hash: str = "fixture-query-hash"
        self.schema_hash: str = "fixture-schema-hash"
        self.executed_queries: int = 0
        self.inspect_calls: int = 0
        self.dry_run_limits: list[int] = []
        self.export_limits: list[int] = []
        self.export_destinations: list[str] = []

    def inspect(self, source: str) -> SourceInspection:
        """Return the pinned fixture schema with discovered location metadata."""
        self.inspect_calls += 1
        contract = SOURCE_CATALOG[source]
        return SourceInspection(
            source=source,
            identity=SourceIdentity(location="US", etag="fixture-etag"),
            columns=contract.columns,
        )

    def dry_run(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        maximum_bytes_billed: int,
    ) -> DryRunEstimate:
        """Return the configured non-executing byte estimate."""
        del sql, parameters
        self.dry_run_limits.append(maximum_bytes_billed)
        return self.estimate

    def export_snapshot(
        self,
        sql: str,
        parameters: tuple[QueryParameter, ...],
        destination_uri: str,
        maximum_bytes_billed: int,
    ) -> SnapshotExport:
        """Record one atomic snapshot export and return its objects and count."""
        del sql, parameters
        self.executed_queries += 1
        self.export_limits.append(maximum_bytes_billed)
        self.export_destinations.append(destination_uri)
        return SnapshotExport(
            row_count=self.snapshot_row_count,
            object_uris=self.snapshot_uris,
        )


class InMemoryManifestStore:
    """Append-only manifest fake with production-equivalent latest selection."""

    def __init__(self, manifests: tuple[BatchManifest, ...] = ()) -> None:
        """Seed immutable manifest history."""
        self.manifests: list[BatchManifest] = list(manifests)

    def latest_completed(self, source: str, year: int) -> BatchManifest | None:
        """Return only the newest completed matching partition."""
        candidates = [
            manifest
            for manifest in self.manifests
            if manifest.source == source
            and manifest.year == year
            and manifest.status is BatchStatus.COMPLETED
            and manifest.completed_at is not None
        ]
        return max(
            candidates,
            key=lambda item: item.completed_at or datetime.min.replace(tzinfo=UTC),
            default=None,
        )

    def persist(self, manifest: BatchManifest) -> None:
        """Append a new immutable checkpoint."""
        self.manifests.append(manifest)


class InMemoryObjectStore:
    """Byte-backed object store fake enforcing generation-match zero."""

    def __init__(self) -> None:
        """Create an isolated empty fake bucket."""
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}
        self.created_objects: int = 0
        self.reused_objects: int = 0

    def seed(self, uri: str, payload: bytes) -> None:
        """Seed landing data outside the production write path."""
        self.objects[uri] = payload
        self.generations[uri] = self.generations.get(uri, 0) + 1

    def read(self, uri: str) -> bytes:
        """Read one seeded object."""
        return self.objects[uri]

    def read_versioned(self, uri: str) -> VersionedPayload:
        """Return bytes with the fake's current object generation."""
        payload = self.objects[uri]
        return VersionedPayload(
            version=ObjectVersion(
                uri=uri,
                generation=self.generations[uri],
                metageneration=1,
                payload_sha256=sha256(payload).hexdigest(),
            ),
            payload=payload,
        )

    def copy_immutable(self, source: ObjectVersion, destination_uri: str) -> BronzeObject:
        """Reject stale sources before creating the fake destination."""
        payload = self.objects[source.uri]
        if (
            self.generations[source.uri] != source.generation
            or sha256(payload).hexdigest() != source.payload_sha256
        ):
            raise StaleObjectGenerationError(uri=source.uri)
        return self.write_immutable(destination_uri, payload)

    def write_immutable(self, uri: str, payload: bytes) -> BronzeObject:
        """Create one object and reject an existing URI."""
        existing = self.objects.get(uri)
        if existing is not None:
            if existing != payload:
                raise ImmutableObjectExistsError(uri=uri)
            self.reused_objects += 1
            return BronzeObject(
                uri=uri,
                generation=1,
                crc32c=crc32c_base64(existing),
                size_bytes=len(existing),
            )
        self.objects[uri] = payload
        self.generations[uri] = 1
        self.created_objects += 1
        return BronzeObject(
            uri=uri,
            generation=1,
            crc32c=crc32c_base64(payload),
            size_bytes=len(payload),
        )


@dataclass(frozen=True, slots=True)
class ContentIdentityFixture:
    """Content identity fields shared by manifest test fixtures."""

    query_hash: str = "query"
    schema_hash: str = "schema"
    fingerprint: str = "fingerprint"


@dataclass(frozen=True, slots=True)
class ManifestFixtureSpec:
    """Typed manifest fixture input without positional parameter bloat."""

    run_id: str
    source: str
    year: int
    status: BatchStatus
    completed_at: datetime | None
    identity: ContentIdentityFixture = field(default_factory=ContentIdentityFixture)


def manifest_fixture(spec: ManifestFixtureSpec) -> BatchManifest:
    """Build a deterministic PII-free manifest for port and release tests."""
    return BatchManifest(
        run_id=spec.run_id,
        source=spec.source,
        year=spec.year,
        status=spec.status,
        source_identity=SourceIdentity(location="US", etag="fixture-etag"),
        row_count=1,
        fingerprint=spec.identity.fingerprint,
        query_hash=spec.identity.query_hash,
        schema_hash=spec.identity.schema_hash,
        bronze_objects=(),
        started_at=datetime(2025, 1, 1, tzinfo=UTC),
        completed_at=spec.completed_at,
        verified_at=spec.completed_at,
        git_sha=sha256(spec.run_id.encode()).hexdigest(),
        image_digest=f"sha256:{sha256(spec.source.encode()).hexdigest()}",
    )
