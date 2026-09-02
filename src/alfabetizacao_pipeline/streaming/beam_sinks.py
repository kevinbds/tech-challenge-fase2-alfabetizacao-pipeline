from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Final, TypedDict

from apache_beam.utils.timestamp import Timestamp

if TYPE_CHECKING:
    from decimal import Decimal

    from alfabetizacao_pipeline.streaming.beam_routes import QuarantineRow, StagedEventRow


class _TableField(TypedDict):
    name: str
    type: str
    mode: str


class _TableSchema(TypedDict):
    fields: list[_TableField]


class ValidStorageRow(TypedDict):
    """Storage Write representation of one valid staging row."""

    event_id: str
    message_id: str
    event_time: Timestamp
    publish_time: Timestamp
    ingestion_time: Timestamp
    ano: int
    id_municipio: str
    rede: str
    taxa_alfabetizacao: Decimal
    taxa_participacao: Decimal | None
    correlation_id: str
    simulation: bool


class QuarantineStorageRow(TypedDict):
    """Storage Write representation of one quarantine row."""

    message_id: str
    reason_code: str
    ingestion_time: Timestamp
    event_fingerprint: str
    correlation_id: str | None


VALID_TABLE_SCHEMA: Final[_TableSchema] = {
    "fields": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "message_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "event_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "publish_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "ingestion_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "ano", "type": "INTEGER", "mode": "REQUIRED"},
        {"name": "id_municipio", "type": "STRING", "mode": "REQUIRED"},
        {"name": "rede", "type": "STRING", "mode": "REQUIRED"},
        {"name": "taxa_alfabetizacao", "type": "NUMERIC", "mode": "REQUIRED"},
        {"name": "taxa_participacao", "type": "NUMERIC", "mode": "NULLABLE"},
        {"name": "correlation_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "simulation", "type": "BOOLEAN", "mode": "REQUIRED"},
    ]
}

QUARANTINE_TABLE_SCHEMA: Final[_TableSchema] = {
    "fields": [
        {"name": "message_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "reason_code", "type": "STRING", "mode": "REQUIRED"},
        {"name": "ingestion_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "event_fingerprint", "type": "STRING", "mode": "REQUIRED"},
        {"name": "correlation_id", "type": "STRING", "mode": "NULLABLE"},
    ]
}


def valid_storage_row(row: StagedEventRow) -> ValidStorageRow:
    """Convert staging timestamps to Storage Write API values."""
    return ValidStorageRow(
        event_id=row["event_id"],
        message_id=row["message_id"],
        event_time=Timestamp.from_utc_datetime(datetime.fromisoformat(row["event_time"])),
        publish_time=Timestamp.from_utc_datetime(datetime.fromisoformat(row["publish_time"])),
        ingestion_time=Timestamp.from_utc_datetime(datetime.fromisoformat(row["ingestion_time"])),
        ano=row["ano"],
        id_municipio=row["id_municipio"],
        rede=row["rede"],
        taxa_alfabetizacao=row["taxa_alfabetizacao"],
        taxa_participacao=row["taxa_participacao"],
        correlation_id=row["correlation_id"],
        simulation=row["simulation"],
    )


def quarantine_storage_row(row: QuarantineRow) -> QuarantineStorageRow:
    """Convert quarantine timestamps to Storage Write API values."""
    return QuarantineStorageRow(
        message_id=row["message_id"],
        reason_code=row["reason_code"],
        ingestion_time=Timestamp.from_utc_datetime(datetime.fromisoformat(row["ingestion_time"])),
        event_fingerprint=row["event_fingerprint"],
        correlation_id=row["correlation_id"],
    )
