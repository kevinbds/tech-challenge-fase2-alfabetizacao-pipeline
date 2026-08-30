from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class AlertNotFoundError(Exception):
    """Raised when an alert identifier is absent from the catalog."""

    alert_id: str

    @override
    def __str__(self) -> str:
        return f"alert not found: {self.alert_id}"


class SloContract(BaseModel):
    """A service-level objective consumed by monitoring automation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    slo_id: str
    objective: Decimal
    window_days: int
    unit: str


class AlertBase(BaseModel):
    """Fields shared by monitored metrics and budget notifications."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    alert_id: str
    comparison: Literal["gt", "gte", "lt", "lte", "abs_gt"]
    threshold: Decimal
    unit: str
    duration_seconds: int
    severity: Literal["warning", "critical"]


class MetricAlert(AlertBase):
    """An alert evaluated from a Cloud Monitoring metric."""

    signal_type: Literal["monitoring_metric"]
    metric_type: str


class BudgetAlert(AlertBase):
    """A billing budget notification delivered through Pub/Sub."""

    signal_type: Literal["budget_notification"]
    notification_topic: str


AlertContract = Annotated[MetricAlert | BudgetAlert, Field(discriminator="signal_type")]


class ObservabilityCatalog(BaseModel):
    """SLIs, SLOs and alerts shared by Terraform and operations."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    notification_channel: str
    slos: tuple[SloContract, ...]
    alerts: tuple[AlertContract, ...]

    def alert(self, alert_id: str) -> AlertContract:
        """Return one alert contract by stable identifier."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                return alert
        raise AlertNotFoundError(alert_id=alert_id)


class ProvenanceContract(BaseModel):
    """Build attestation and SBOM requirements."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    required: bool
    sbom_when_available: bool


class TeardownContract(BaseModel):
    """Safety gates required before destructive teardown."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    requires_confirmation: bool
    drain_streaming_first: bool
    allowed_terminal_state: Literal["DRAINED"]
    preserve_state_backup: bool


class RunContracts(BaseModel):
    """Immutable-image, provenance and teardown run contracts."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    version: str
    image_reference_pattern: str
    require_git_sha: bool
    require_build_id: bool
    provenance: ProvenanceContract
    teardown: TeardownContract
    forbidden_log_fields: tuple[str, ...]


def load_observability(path: Path) -> ObservabilityCatalog:
    """Parse the JSON-compatible YAML observability contract."""
    return ObservabilityCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def load_run_contracts(path: Path) -> RunContracts:
    """Parse immutable build and teardown contracts."""
    return RunContracts.model_validate_json(path.read_text(encoding="utf-8"))
