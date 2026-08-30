from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from alfabetizacao_pipeline.streaming.avro_codec import AvroRecord


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
