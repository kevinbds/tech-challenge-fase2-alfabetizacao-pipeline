from datetime import date
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_BYTES_BILLED = 25 * 1024**3
Money = Annotated[Decimal, Field(ge=0, decimal_places=6)]
UnitRate = Annotated[Decimal, Field(ge=0)]
ExchangeRate = Annotated[Decimal, Field(gt=0, decimal_places=6)]
StorageGbMonth = Annotated[Decimal, Field(ge=0)]
GcsOperationBatches = Annotated[Decimal, Field(ge=0)]
DataflowRuntimeHours = Annotated[Decimal, Field(ge=0, le=24)]
BigQueryStorageWriteApiGib = Annotated[Decimal, Field(ge=0)]
BigQueryActiveStorageGibMonth = Annotated[Decimal, Field(ge=0)]
DataflowWorkerMemoryGib = Annotated[Decimal, Field(ge=0)]
DataflowDiskGib = Annotated[Decimal, Field(ge=0)]
StreamingEngineComputeUnitHours = Annotated[Decimal, Field(ge=0)]
PubSubPublishDeliveryGib = Annotated[Decimal, Field(ge=0)]
PubSubGcsExportGib = Annotated[Decimal, Field(ge=0)]
PubSubRetainedGibMonth = Annotated[Decimal, Field(ge=0)]
CloudRunVcpuSeconds = Annotated[Decimal, Field(ge=0)]
CloudRunGibSeconds = Annotated[Decimal, Field(ge=0)]
WorkflowSteps = Annotated[int, Field(ge=0)]
SchedulerJobsMonth = Annotated[Decimal, Field(ge=0)]
ArtifactRegistryGibMonth = Annotated[Decimal, Field(ge=0)]
CloudBuildMinutes = Annotated[Decimal, Field(ge=0)]
LoggingGib = Annotated[Decimal, Field(ge=0)]
MonitoringMib = Annotated[Decimal, Field(ge=0)]
NetworkEgressGib = Annotated[Decimal, Field(ge=0)]
CrossRegionDataTransferGib = Annotated[Decimal, Field(ge=0)]
ImageReference = Annotated[str, StringConstraints(pattern=r"^.+@sha256:[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


@unique
class Currency(StrEnum):
    """Prevent unpriced currency variants from reaching the estimator."""

    BRL = "BRL"


class CostRequest(BaseModel):
    """Make every priced workload component explicit and non-negative."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    currency: Currency
    bigquery_total_bytes_processed: int = Field(ge=0)
    bigquery_query_count: int = Field(ge=1)
    bigquery_max_bytes_billed_per_query: int = Field(gt=0, le=MAX_BYTES_BILLED)
    bigquery_storage_write_api_gib: BigQueryStorageWriteApiGib
    bigquery_active_storage_gib_month: BigQueryActiveStorageGibMonth
    dataflow_max_workers: int = Field(ge=1, le=2)
    dataflow_runtime_hours: DataflowRuntimeHours
    dataflow_worker_vcpus: int = Field(ge=1)
    dataflow_worker_memory_gib: DataflowWorkerMemoryGib
    dataflow_disk_gib: DataflowDiskGib
    dataflow_streaming_engine_compute_unit_hours: StreamingEngineComputeUnitHours
    gcs_storage_gib_month: StorageGbMonth
    gcs_replication_written_gib: StorageGbMonth
    gcs_class_a_operations_per_1000: GcsOperationBatches
    gcs_class_b_operations_per_1000: GcsOperationBatches
    pubsub_publish_delivery_gib: PubSubPublishDeliveryGib
    pubsub_gcs_export_gib: PubSubGcsExportGib
    pubsub_retained_gib_month: PubSubRetainedGibMonth
    cloud_run_vcpu_seconds: CloudRunVcpuSeconds
    cloud_run_gib_seconds: CloudRunGibSeconds
    workflows_internal_steps: WorkflowSteps
    scheduler_jobs_month: SchedulerJobsMonth
    artifact_registry_gib_month: ArtifactRegistryGibMonth
    cloud_build_build_images_minutes: CloudBuildMinutes
    cloud_build_verify_images_minutes: CloudBuildMinutes
    logging_gib: LoggingGib
    monitoring_mib: MonitoringMib
    network_egress_gib: NetworkEgressGib
    cross_region_data_transfer_gib: CrossRegionDataTransferGib


class UnitRates(BaseModel):
    """Version monetary assumptions independently from workload quantities."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    bigquery_per_tib: UnitRate
    bigquery_storage_write_api_per_gib: UnitRate
    bigquery_active_storage_per_gib_month: UnitRate
    dataflow_vcpu_per_hour: UnitRate
    dataflow_memory_per_gib_hour: UnitRate
    dataflow_standard_pd_per_gib_hour: UnitRate
    dataflow_streaming_engine_compute_unit_hour: UnitRate
    gcs_storage_per_gib_month: UnitRate
    gcs_replication_per_gib: UnitRate
    gcs_class_a_operations_per_1000: UnitRate
    gcs_class_b_operations_per_1000: UnitRate
    pubsub_publish_delivery_per_gib: UnitRate
    pubsub_gcs_export_per_gib: UnitRate
    pubsub_retention_per_gib_month: UnitRate
    cloud_run_vcpu_second: UnitRate
    cloud_run_gib_second: UnitRate
    workflows_internal_steps_per_1000: UnitRate
    scheduler_per_job_month: UnitRate
    artifact_registry_per_gib_month: UnitRate
    cloud_build_build_images_per_minute: UnitRate
    cloud_build_verify_images_per_minute: UnitRate
    logging_per_gib: UnitRate
    monitoring_per_mib: UnitRate
    network_egress_per_gib: UnitRate
    cross_region_data_transfer_per_gib: UnitRate


class CostCatalog(BaseModel):
    """Versioned FinOps assumptions and named workload profiles."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    bigquery_location: Literal["US"]
    runtime_location: Literal["us-central1"]
    storage_location: Literal["us-central1"]
    rates: UnitRates
    profiles: dict[str, CostRequest]
    budget_amount: Money
    budget_is_hard_cap: bool
    usd_to_brl: ExchangeRate
    usd_to_brl_as_of: date
    rate_basis: Literal["gross_without_free_tier"]
    min_instances: int = Field(ge=0, le=0)
    bronze_storage_class: str
    landing_retention_days: int = Field(ge=1)
    streaming_retention_days: int = Field(ge=1)


class CostReport(BaseModel):
    """Serialize billed components beside their units and pricing assumptions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    profile: str
    currency: Currency
    bigquery_location: Literal["US"]
    runtime_location: Literal["us-central1"]
    storage_location: Literal["us-central1"]
    bigquery: Money
    bigquery_storage_write_api: Money
    bigquery_active_storage: Money
    dataflow: Money
    dataflow_vcpu: Money
    dataflow_memory: Money
    dataflow_persistent_disk: Money
    dataflow_streaming_engine: Money
    storage: Money
    gcs_storage: Money
    gcs_replication: Money
    gcs_class_a_operations: Money
    gcs_class_b_operations: Money
    pubsub: Money
    pubsub_publish_delivery: Money
    pubsub_gcs_export: Money
    pubsub_retention: Money
    cloud_run: Money
    workflows: Money
    scheduler: Money
    artifact_registry: Money
    cloud_build: Money
    cloud_build_build_images: Money
    cloud_build_verify_images: Money
    logging: Money
    monitoring: Money
    network_egress: Money
    cross_region_data_transfer: Money
    total: Money
    bytes_unit: str = "byte"
    bigquery_storage_write_api_unit: str = "GiB"
    bigquery_active_storage_unit: str = "GiB-month"
    dataflow_vcpu_unit: str = "vCPU-hour"
    dataflow_memory_unit: str = "GiB-hour"
    dataflow_persistent_disk_unit: str = "GiB-hour"
    dataflow_streaming_engine_unit: str = "compute-unit-hour"
    gcs_storage_unit: str = "GiB-month"
    gcs_replication_unit: str = "GiB written"
    gcs_operations_unit: str = "1,000 operations"
    pubsub_publish_delivery_unit: str = "GiB"
    pubsub_gcs_export_unit: str = "GiB"
    pubsub_retention_unit: str = "GiB-month"
    cloud_run_cpu_unit: str = "vCPU-second"
    cloud_run_memory_unit: str = "GiB-second"
    workflow_internal_unit: str = "1,000 internal steps"
    scheduler_unit: str = "job-month"
    artifact_registry_unit: str = "GiB-month"
    cloud_build_unit: str = "minute"
    logging_unit: str = "GiB"
    monitoring_unit: str = "MiB"
    network_egress_unit: str = "GiB"
    cross_region_data_transfer_unit: str = "GiB"
    usd_to_brl: ExchangeRate
    usd_to_brl_as_of: date
    rate_basis: Literal["gross_without_free_tier"]
    bigquery_query_count: int
    max_bytes_billed_per_query: int
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
