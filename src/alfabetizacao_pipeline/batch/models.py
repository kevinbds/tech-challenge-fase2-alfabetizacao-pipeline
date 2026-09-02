from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError


@unique
class BatchStatus(StrEnum):
    """Lifecycle states persisted by a batch run."""

    PLANNED = "planned"
    SKIPPED = "skipped"
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class SelectionPolicy(StrEnum):
    """Partition selection semantics used by a source contract."""

    ANNUAL = "annual"
    SNAPSHOT = "snapshot"


@unique
class BigQueryType(StrEnum):
    """Closed source types supported by the extraction contracts."""

    INT64 = "INT64"
    FLOAT64 = "FLOAT64"
    STRING = "STRING"


class SourceColumn(BaseModel):
    """Pinned BigQuery column name, type and mode."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    data_type: BigQueryType
    mode: str = "NULLABLE"


class SourceContract(BaseModel):
    """Versioned extraction contract for one official source."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    columns: tuple[SourceColumn, ...]
    key_columns: tuple[str, ...]
    selection_policy: SelectionPolicy
    pinned_schema_commit: str


class SourceIdentity(BaseModel):
    """Runtime source provenance discovered from BigQuery metadata."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    location: str
    modified_at: datetime | None = None
    etag: str | None = None


class SourceInspection(BaseModel):
    """Runtime metadata and schema returned by source inspection."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    identity: SourceIdentity
    columns: tuple[SourceColumn, ...]


class DryRunEstimate(BaseModel):
    """Bytes processed reported by a non-executing BigQuery dry-run."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    bytes_processed: Annotated[int, Field(ge=0)]


class ContentFingerprint(BaseModel):
    """Partition row count and deterministic content fingerprint."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    row_count: Annotated[int, Field(gt=0)]
    value: str


class SnapshotExport(BaseModel):
    """Objects and row count produced by one atomic snapshot job."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    row_count: Annotated[int, Field(gt=0)]
    object_uris: Annotated[tuple[str, ...], Field(min_length=1)]


class QueryParameter(BaseModel):
    """Named scalar bound separately from BigQuery SQL text."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    data_type: BigQueryType
    value: int | str


class BronzeObject(BaseModel):
    """Integrity metadata of one immutable Bronze object generation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    uri: str = Field(pattern=r"^gs://")
    generation: Annotated[int, Field(gt=0)]
    crc32c: str
    size_bytes: Annotated[int, Field(ge=0)]


class ObjectVersion(BaseModel):
    """Pinned generation and digest for one object already read."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    uri: str = Field(pattern=r"^gs://")
    generation: Annotated[int, Field(gt=0)]
    metageneration: Annotated[int, Field(gt=0)]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VersionedPayload(BaseModel):
    """Bytes downloaded with generation preconditions and their identity."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    version: ObjectVersion
    payload: bytes


class BatchManifest(BaseModel):
    """PII-free provenance record for one source partition run."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    run_id: str
    attempt_id: str | None = None
    source: str
    year: Annotated[int, Field(ge=2000, le=2100)]
    status: BatchStatus
    source_identity: SourceIdentity
    row_count: Annotated[int, Field(gt=0)]
    fingerprint: str
    query_hash: str
    schema_hash: str
    bronze_objects: tuple[BronzeObject, ...]
    started_at: datetime
    completed_at: datetime | None
    verified_at: datetime | None
    git_sha: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    image_digest: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

    @model_validator(mode="after")
    def reject_pii(self) -> "BatchManifest":
        """Reject student identifiers from operational metadata."""
        serialized = self.model_dump_json()
        if "id_aluno" in serialized:
            error_code = "pii_metadata"
            message = "manifest metadata must not contain student identifiers"
            raise PydanticCustomError(
                error_code,
                message,
            )
        return self


class BatchRequest(BaseModel):
    """Validated user request to plan or execute one annual partition."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    year: Annotated[int, Field(ge=2000, le=2100)]
    maximum_bytes_billed: Annotated[int, Field(gt=0)] = 25 * 1024**3
    dry_run: bool = True


class BatchPlan(BaseModel):
    """Machine-readable execution planning decision with content identity."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    run_id: str
    source: str
    year: int
    status: BatchStatus
    estimated_bytes: int
    maximum_bytes_billed: int
    query_hash: str
    schema_hash: str
    fingerprint: str
    row_count: int
    cloud_writes: int = 0


class BatchEstimate(BaseModel):
    """Machine-readable dry-run estimate without a content identity query."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    year: int
    status: BatchStatus = BatchStatus.PLANNED
    estimated_bytes: int
    maximum_bytes_billed: int
    query_hash: str
    schema_hash: str
    cloud_writes: int = 0


class BatchRunContext(BaseModel):
    """Immutable deployment provenance and storage prefixes for execution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    landing_prefix: str = Field(pattern=r"^gs://")
    bronze_prefix: str = Field(pattern=r"^gs://")
    git_sha: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    image_digest: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DeploymentProvenance(BaseModel):
    """Validated non-empty deployment identity loaded before SDK composition."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    git_sha: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    image_digest: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SchemaDriftReport(BaseModel):
    """Additive warnings and blocking incompatible schema changes."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    blocking: bool
    removed_columns: tuple[str, ...]
    added_columns: tuple[str, ...]
    type_changes: tuple[str, ...]
    mode_changes: tuple[str, ...]
