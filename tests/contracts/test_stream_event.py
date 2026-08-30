from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.streaming.avro_codec import (
    AvroContractError,
    decode_event,
    encode_event,
)
from alfabetizacao_pipeline.streaming.models import MunicipalLiteracyRateUpdatedV1


def valid_payload() -> dict[str, str | int | float | bool | None]:
    return {
        "schema_version": "1.0",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "event_type": "municipal_literacy_rate.updated",
        "simulation": True,
        "event_time": "2026-08-29T12:00:00Z",
        "ano": 2025,
        "id_municipio": "3550308",
        "rede": "total",
        "taxa_alfabetizacao": 91.25,
        "participacao": 88.5,
        "producer": "fixture-v1",
        "correlation_id": "demo-20260829",
    }


def test_roundtrip_preserves_contract_when_payload_is_valid() -> None:
    # Given a boundary payload that satisfies Avro and semantic constraints
    event = MunicipalLiteracyRateUpdatedV1.model_validate(valid_payload())

    # When it is serialized and decoded through the checked Avro codec
    decoded = decode_event(encode_event(event.model_dump(mode="json")))

    # Then the typed event and its UTC instant are preserved
    assert decoded.event_id == UUID("00000000-0000-4000-8000-000000000001")
    assert decoded.event_time == datetime(2026, 8, 29, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ano", 1999),
        ("ano", 2101),
        ("id_municipio", "355030"),
        ("taxa_alfabetizacao", 100.01),
        ("participacao", -0.01),
        ("simulation", False),
        ("event_time", "2026-08-29T12:00:00-03:00"),
    ],
)
def test_semantic_contract_rejects_invalid_value_when_avro_shape_is_compatible(
    field: str, value: str | float | bool
) -> None:
    # Given an Avro-compatible record with one semantic violation
    payload = valid_payload()
    payload[field] = value

    # When semantic parsing occurs, then the boundary rejects it
    with pytest.raises(ValidationError):
        _ = MunicipalLiteracyRateUpdatedV1.model_validate(payload)


def test_avro_contract_rejects_incompatible_record_before_publish() -> None:
    # Given a record without a required Avro field
    payload = valid_payload()
    del payload["event_id"]

    # When the producer codec checks it, then no bytes are produced
    with pytest.raises(AvroContractError):
        _ = encode_event(payload)


def test_schema_artifact_exists_at_the_pinned_contract_path() -> None:
    # Given the repository contract path
    schema = Path("schemas/events/MunicipalLiteracyRateUpdatedV1.avsc")

    # When the repository is packaged, then the schema remains versioned
    assert schema.is_file()
