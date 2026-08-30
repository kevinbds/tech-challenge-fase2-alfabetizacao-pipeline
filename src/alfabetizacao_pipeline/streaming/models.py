from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, ClassVar, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


@unique
class Rede(StrEnum):
    """Categorias de rede aceitas pela fonte oficial."""

    TOTAL = "total"
    ESTADUAL = "estadual"
    MUNICIPAL = "municipal"
    PUBLICA = "publica"


def _require_utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        msg = "event_time precisa conter offset UTC explícito"
        raise ValueError(msg)
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]
MunicipalityId = Annotated[str, StringConstraints(pattern=r"^\d{7}$")]
Percentage = Annotated[float, Field(ge=0, le=100)]


class MunicipalLiteracyRateUpdatedV1(BaseModel):
    """Evento imutável de atualização municipal usado apenas em simulação."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"]
    event_id: UUID
    event_type: Literal["municipal_literacy_rate.updated"]
    simulation: Literal[True]
    event_time: UtcDateTime
    ano: Annotated[int, Field(ge=2000, le=2100)]
    id_municipio: MunicipalityId
    rede: Rede
    taxa_alfabetizacao: Percentage
    participacao: Percentage | None = None
    producer: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    correlation_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def reject_sentinel_municipality(self) -> Self:
        """Impede que o identificador sentinela atravesse a fronteira semântica."""
        if self.id_municipio == "0000000":
            msg = "id_municipio sentinela não representa município real"
            raise ValueError(msg)
        return self
