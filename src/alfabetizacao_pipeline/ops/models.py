from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_BYTES_BILLED = 25 * 1024**3
Money = Annotated[Decimal, Field(ge=0, decimal_places=6)]
WorkerHours = Annotated[Decimal, Field(ge=0, le=24)]
StorageGbMonth = Annotated[Decimal, Field(ge=0)]
PubSubGib = Annotated[Decimal, Field(ge=0)]
ImageReference = Annotated[str, StringConstraints(pattern=r"^.+@sha256:[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


@unique
class Currency(StrEnum):
    """Currencies approved for the local baseline."""

    BRL = "BRL"


class CostRequest(BaseModel):
    """Validated workload quantities for one estimate."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    currency: Currency
    bytes_processed: int = Field(ge=0, le=MAX_BYTES_BILLED)
    workers: int = Field(ge=1, le=2)
    worker_hours: WorkerHours
    storage_gb_month: StorageGbMonth
    pubsub_gib: PubSubGib


class UnitRates(BaseModel):
    """BRL unit prices used by the deterministic estimator."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    bigquery_per_tib: Money
    dataflow_per_worker_hour: Money
    storage_per_gb_month: Money
    pubsub_per_gib: Money


class CostCatalog(BaseModel):
    """Versioned FinOps assumptions and named workload profiles."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    rates: UnitRates
    profiles: dict[str, CostRequest]
    budget_amount: Money
    budget_is_hard_cap: bool
    min_instances: int = Field(ge=0, le=0)
    bronze_storage_class: str
    landing_retention_days: int = Field(ge=1)
    streaming_retention_days: int = Field(ge=1)


class CostReport(BaseModel):
    """Machine-readable estimate with explicit units and assumptions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    profile: str
    currency: Currency
    bigquery: Money
    dataflow: Money
    storage: Money
    pubsub: Money
    total: Money
    bytes_unit: str = "byte"
    worker_time_unit: str = "worker-hour"
    storage_unit: str = "GB-month"
    pubsub_unit: str = "GiB"
    max_bytes_billed: int = MAX_BYTES_BILLED
    worker_range: str = "1..2"
    min_instances: int = 0
    budget_is_hard_cap: bool = False


class RunIdentity(BaseModel):
    """Immutable image and source identity required by every cloud run."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    image_reference: ImageReference
    git_sha: GitSha
    build_id: str = Field(min_length=1)


class InvalidCostResponse(BaseModel):
    """Stable error response that never serializes rejected input values."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal["invalid"] = "invalid"
    error_code: Literal["invalid_cost_catalog", "profile_not_found"]
    error_count: int = Field(ge=1)
