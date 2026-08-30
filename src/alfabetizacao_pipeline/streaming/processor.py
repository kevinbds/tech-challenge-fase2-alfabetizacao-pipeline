from dataclasses import dataclass
from statistics import quantiles

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, decode_event
from alfabetizacao_pipeline.streaming.envelope import (
    DuplicateAudit,
    MessageEnvelope,
    QuarantinedMessage,
    ValidMessage,
)


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """Saídas separadas do processamento streaming local."""

    raw: tuple[MessageEnvelope, ...]
    valid: tuple[ValidMessage, ...]
    duplicates: tuple[DuplicateAudit, ...]
    quarantine: tuple[QuarantinedMessage, ...]
    redelivery_count: int
    p95_latency_seconds: float


def process_messages(messages: tuple[MessageEnvelope, ...]) -> ProcessingResult:
    """Deduplica redelivery e evento, isolando entradas semanticamente inválidas."""
    physical_unique: dict[str, MessageEnvelope] = {}
    for message in messages:
        _ = physical_unique.setdefault(message.message_id, message)

    valid_by_event: dict[str, ValidMessage] = {}
    duplicates: list[DuplicateAudit] = []
    quarantine: list[QuarantinedMessage] = []
    latencies: list[float] = []

    for message in physical_unique.values():
        try:
            event = decode_event(message.payload)
        except AvroContractError:
            quarantine.append(
                QuarantinedMessage(message_id=message.message_id, reason_code="SEMANTIC_INVALID")
            )
            continue
        candidate = ValidMessage(
            message_id=message.message_id,
            event=event,
            publish_time=message.publish_time,
            ingestion_time=message.ingestion_time,
        )
        event_id = str(event.event_id)
        canonical = valid_by_event.get(event_id)
        if canonical is None:
            valid_by_event[event_id] = candidate
        else:
            ordered = sorted(
                (canonical, candidate),
                key=lambda item: (item.event.event_time, item.publish_time, item.ingestion_time),
                reverse=True,
            )
            valid_by_event[event_id] = ordered[0]
            duplicates.append(
                DuplicateAudit(
                    message_id=ordered[1].message_id,
                    canonical_message_id=ordered[0].message_id,
                    event_id=event_id,
                )
            )
        latencies.append((message.ingestion_time - message.publish_time).total_seconds())

    p95 = quantiles(latencies, n=100, method="inclusive")[94] if latencies else 0.0
    return ProcessingResult(
        raw=tuple(physical_unique.values()),
        valid=tuple(sorted(valid_by_event.values(), key=lambda item: str(item.event.event_id))),
        duplicates=tuple(duplicates),
        quarantine=tuple(quarantine),
        redelivery_count=len(messages) - len(physical_unique),
        p95_latency_seconds=p95,
    )
