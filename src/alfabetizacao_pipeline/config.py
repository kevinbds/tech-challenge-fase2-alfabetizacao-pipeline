from decimal import Decimal
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

from alfabetizacao_pipeline.types import BytesBilled, ProjectId

PositiveBytes = Annotated[int, Field(gt=0)]
PositiveMoney = Annotated[Decimal, Field(gt=0)]
GcpProjectIdInput = Annotated[
    str,
    StringConstraints(
        min_length=6,
        max_length=30,
        pattern=r"^[a-z][a-z0-9-]*[a-z0-9]$",
    ),
]
GcpRegionInput = Annotated[
    str,
    StringConstraints(
        min_length=5,
        max_length=63,
        pattern=r"^[a-z]+(?:-[a-z]+)+[1-9][0-9]*$",
    ),
]


class AppSettings(BaseSettings):
    """Validated, immutable configuration loaded from local environment values."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="ALFABETIZACAO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    gcp_project_id: GcpProjectIdInput = "local-project"
    gcp_region: GcpRegionInput = "southamerica-east1"
    bigquery_location: str = Field(default="US", min_length=1)
    source_project_id: str = Field(default="basedosdados", min_length=1)
    source_dataset_id: str = Field(
        default="br_inep_avaliacao_alfabetizacao",
        min_length=1,
    )
    max_bytes_billed: PositiveBytes = 25 * 1024**3
    budget_amount: PositiveMoney = Decimal(50)
    budget_currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")

    @property
    def project_id(self) -> ProjectId:
        """Return the validated project identifier as a domain-specific type."""
        return ProjectId(self.gcp_project_id)

    @property
    def bytes_billed_limit(self) -> BytesBilled:
        """Return the validated query cap as a domain-specific type."""
        return BytesBilled(self.max_bytes_billed)


class ConfigCheck(BaseModel):
    """Machine-readable result returned by the configuration command."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    config: AppSettings
