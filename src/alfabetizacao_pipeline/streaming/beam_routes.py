from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, ClassVar, TypedDict

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, decode_event

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    class _DoFn:
        pass

    @dataclass(frozen=True, slots=True)
    class _TaggedOutput[RowT]:
        tag: str
        value: RowT

else:
    from apache_beam import DoFn as _DoFn
    from apache_beam.pvalue import TaggedOutput as _TaggedOutput


@dataclass(frozen=True, slots=True)
class BeamEnvelope:
    """Payload Pub/Sub e metadados necessários ao staging determinístico."""

    message_id: str
    payload: bytes
    publish_time: datetime
    ingestion_time: datetime


class StagedEventRow(TypedDict):
    """Linha de staging necessária ao dedupe pós-drain."""

    event_id: str
    message_id: str
    event_time: str
    publish_time: str
    ingestion_time: str
    ano: int
    id_municipio: str
    rede: str
    taxa_alfabetizacao: float
    participacao: float | None
    correlation_id: str
    simulation: bool


class QuarantineRow(TypedDict):
    """Referência segura a um evento recusado."""

    message_id: str
    ingestion_time: str
    reason_code: str


@unique
class QuarantineReason(StrEnum):
    """Motivo estável de roteamento para a quarentena."""

    AVRO_OR_SEMANTIC_INVALID = "AVRO_OR_SEMANTIC_INVALID"


class RouteEventDoFn(_DoFn):
    """Valida Avro e semântica dentro do Beam, com quarentena lateral."""

    VALID: ClassVar[str] = "valid"
    QUARANTINE: ClassVar[str] = "quarantine"

    def process(
        self, envelope: BeamEnvelope
    ) -> Iterator[StagedEventRow | _TaggedOutput[QuarantineRow]]:
        """Emite staging válido ou uma referência segura de quarentena."""
        try:
            event = decode_event(envelope.payload)
        except AvroContractError:
            yield _TaggedOutput(
                self.QUARANTINE,
                QuarantineRow(
                    message_id=envelope.message_id,
                    ingestion_time=envelope.ingestion_time.isoformat(),
                    reason_code=QuarantineReason.AVRO_OR_SEMANTIC_INVALID,
                ),
            )
            return
        yield StagedEventRow(
            event_id=str(event.event_id),
            message_id=envelope.message_id,
            event_time=event.event_time.isoformat(),
            publish_time=envelope.publish_time.isoformat(),
            ingestion_time=envelope.ingestion_time.isoformat(),
            ano=event.ano,
            id_municipio=event.id_municipio,
            rede=event.rede,
            taxa_alfabetizacao=event.taxa_alfabetizacao,
            participacao=event.participacao,
            correlation_id=event.correlation_id,
            simulation=event.simulation,
        )
