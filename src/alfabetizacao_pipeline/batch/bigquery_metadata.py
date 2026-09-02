from collections.abc import Sequence
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from alfabetizacao_pipeline.batch.models import BigQueryType, SourceColumn

BIGQUERY_TYPE_ALIASES: Final[dict[str, BigQueryType]] = {
    "INT64": BigQueryType.INT64,
    "INTEGER": BigQueryType.INT64,
    "FLOAT64": BigQueryType.FLOAT64,
    "FLOAT": BigQueryType.FLOAT64,
    "STRING": BigQueryType.STRING,
}
SUPPORTED_COLUMN_MODES: Final[frozenset[str]] = frozenset({"NULLABLE", "REQUIRED"})


@runtime_checkable
class BigQuerySchemaField(Protocol):
    """Fields exposed by BigQuery table metadata."""

    @property
    def name(self) -> str:
        """Return the column name."""
        ...

    @property
    def field_type(self) -> str:
        """Return the BigQuery data type."""
        ...

    @property
    def mode(self) -> str:
        """Return the BigQuery nullability mode."""
        ...


@runtime_checkable
class BigQueryTableMetadata(Protocol):
    """Table metadata needed to establish extraction provenance."""

    @property
    def schema(self) -> Sequence[BigQuerySchemaField]:
        """Return fields in declared ordinal order."""
        ...

    @property
    def modified(self) -> datetime | None:
        """Return the source modification timestamp when available."""
        ...

    @property
    def etag(self) -> str | None:
        """Return the metadata entity tag when available."""
        ...


def source_column_from_metadata(field: BigQuerySchemaField) -> SourceColumn:
    """Normalize one supported metadata field into the extraction contract."""
    data_type = BIGQUERY_TYPE_ALIASES.get(field.field_type.upper())
    if data_type is None:
        message = f"unsupported-source-column-type:{field.field_type}"
        raise ValueError(message)
    mode = field.mode.upper()
    if mode not in SUPPORTED_COLUMN_MODES:
        message = f"unsupported-source-column-mode:{field.mode}"
        raise ValueError(message)
    return SourceColumn(name=field.name, data_type=data_type, mode=mode)
