from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from containers.dataflow.beam_entrypoint import pubsub_envelope

from alfabetizacao_pipeline.streaming.beam_routes import BeamEnvelope, quarantine_row


@dataclass(frozen=True, slots=True)
class _PubsubMessage:
    data: bytes
    attributes: dict[str, str]
    message_id: str | None = None
    publish_time: datetime | None = None


def test_pubsub_envelope_preserves_correlation_for_invalid_payload() -> None:
    message = _PubsubMessage(b"not-avro", {"correlation_id": "demo-run-42"})
    envelope = pubsub_envelope(message)
    assert envelope.correlation_id == "demo-run-42"


def test_quarantine_fingerprint_is_stable_across_publish_retries() -> None:
    instant = datetime(2026, 8, 30, 12, tzinfo=UTC)
    payload = b"not-avro"
    rows = [
        quarantine_row(
            BeamEnvelope(
                message_id=message_id,
                payload=payload,
                publish_time=instant,
                ingestion_time=instant,
                correlation_id="demo-run-42",
            )
        )
        for message_id in ("publish-1", "publish-2")
    ]

    assert {row["message_id"] for row in rows} == {"publish-1", "publish-2"}
    assert {row["event_fingerprint"] for row in rows} == {sha256(payload).hexdigest()}
