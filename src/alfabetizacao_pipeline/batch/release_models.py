from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


@unique
class ReleaseStatus(StrEnum):
    """Immutable lifecycle states for one data release."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"


class StorageLocations(BaseModel):
    """Terraform-provided GCS prefixes used by the cloud Batch runtime."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    landing_prefix: str = Field(pattern=r"^gs://[a-z0-9._-]+/landing/batch$")
    bronze_prefix: str = Field(pattern=r"^gs://[a-z0-9._-]+/bronze$")
    manifest_prefix: str = Field(pattern=r"^gs://[a-z0-9._-]+/manifests$")


class ReleaseExecution(BaseModel):
    """Validated release identity for one reference year."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    release_id: str = Field(pattern=r"^batch-[0-9]{6}-y[0-9]{4}-r[a-z0-9]{8,32}$")
    year: Annotated[int, Field(ge=2000, le=2100)]

    @model_validator(mode="after")
    def require_identifier_year(self) -> "ReleaseExecution":
        """Reject executions whose requested year changes the release identity."""
        identifier_year = int(self.release_id.split("-")[2][1:])
        if self.year != identifier_year:
            error_code = "release_year_mismatch"
            message = "release reference year must match the release identifier"
            raise PydanticCustomError(
                error_code,
                message,
            )
        return self


class ReleaseFileMapping(BaseModel):
    """Exact immutable Bronze object selected by one release."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    release_id: str
    table_name: str
    year: int
    file_uri: str
    source_run_id: str
    row_count: Annotated[int, Field(gt=0)]
    generation: Annotated[int, Field(gt=0)]
    crc32c: str
    ingested_at: datetime
    verified_at: datetime


class ReleaseSnapshot(BaseModel):
    """Observable release state returned by release-store operations."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    release_id: str
    year: int
    status: ReleaseStatus
    baseline_release_id: str
    files: tuple[ReleaseFileMapping, ...]
