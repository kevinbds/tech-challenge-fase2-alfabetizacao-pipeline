from datetime import timedelta
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from alfabetizacao_pipeline.streaming.avro_codec import AvroRecord
from alfabetizacao_pipeline.streaming.models import UtcDateTime


class AvroTransportRecord(BaseModel):
    """Forma estrutural aceita pelo schema antes da validação semântica."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    event_id: str
    event_type: str
    simulation: bool
    event_time: str
    ano: int
    id_municipio: str
    rede: str
    taxa_alfabetizacao: float
    participacao: float | None
    producer: str
    correlation_id: str

    def as_avro_record(self) -> AvroRecord:
        """Converte campos tipados no mapa exigido pelo codec."""
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "simulation": self.simulation,
            "event_time": self.event_time,
            "ano": self.ano,
            "id_municipio": self.id_municipio,
            "rede": self.rede,
            "taxa_alfabetizacao": self.taxa_alfabetizacao,
            "participacao": self.participacao,
            "producer": self.producer,
            "correlation_id": self.correlation_id,
        }


class DemoFixture(BaseModel):
    """Documento tipado com mensagens aceitas e uma mensagem incompatível."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    accepted: tuple[AvroTransportRecord, ...]
    schema_incompatible: dict[str, str | int | float | bool | None]


class ReleaseContext(BaseModel):
    """Ano de negócio e relógio UTC usados por uma execução do demo."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    target_year: Annotated[int, Field(ge=2000, le=2100)]
    base_time: UtcDateTime
    correlation_id: Annotated[str | None, Field(min_length=1, max_length=128)] = None


def accepted_records_for_release(
    fixture: DemoFixture, release: ReleaseContext
) -> tuple[AvroRecord, ...]:
    """Aplica ano, tempo e correlação da execução sem alterar a ordem da fixture."""
    prepared: list[AvroRecord] = []
    for index, record in enumerate(fixture.accepted, start=1):
        avro_record = record.as_avro_record()
        avro_record["ano"] = release.target_year
        event_time = release.base_time + timedelta(seconds=index)
        avro_record["event_time"] = event_time.isoformat().replace("+00:00", "Z")
        if release.correlation_id is not None:
            avro_record["correlation_id"] = release.correlation_id
        prepared.append(avro_record)
    return tuple(prepared)
