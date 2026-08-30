from dataclasses import dataclass
from datetime import datetime

from alfabetizacao_pipeline.streaming.models import MunicipalLiteracyRateUpdatedV1


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Mensagem Pub/Sub com metadados necessários para ordenação e auditoria."""

    message_id: str
    payload: bytes
    publish_time: datetime
    ingestion_time: datetime


@dataclass(frozen=True, slots=True)
class ValidMessage:
    """Mensagem já convertida no contrato semântico."""

    message_id: str
    event: MunicipalLiteracyRateUpdatedV1
    publish_time: datetime
    ingestion_time: datetime


@dataclass(frozen=True, slots=True)
class QuarantinedMessage:
    """Referência segura a uma mensagem recusada sem reter o payload."""

    message_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class DuplicateAudit:
    """Relação entre uma duplicata de negócio e sua mensagem canônica."""

    message_id: str
    canonical_message_id: str
    event_id: str
