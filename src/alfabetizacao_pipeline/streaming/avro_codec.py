import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, override

from pydantic import ValidationError

from alfabetizacao_pipeline.streaming.models import MunicipalLiteracyRateUpdatedV1

type Scalar = str | int | float | bool | None
type AvroRecord = dict[str, Scalar]
type SchemaValue = str | bool | list["SchemaValue"] | dict[str, "SchemaValue"] | None
type AvroSchema = dict[str, SchemaValue]

if TYPE_CHECKING:

    class _FastAvro(Protocol):
        def parse_schema(self, schema: AvroSchema) -> AvroSchema: ...

        def schemaless_writer(
            self, stream: io.BytesIO, schema: AvroSchema, record: AvroRecord, *, strict: bool
        ) -> None: ...

        def schemaless_reader(self, stream: io.BytesIO, schema: AvroSchema) -> AvroRecord: ...

    _fastavro: _FastAvro

else:
    import fastavro as _fastavro


SCHEMA: AvroSchema = {
    "type": "record",
    "name": "MunicipalLiteracyRateUpdatedV1",
    "namespace": "br.fiap.alfabetizacao.events.v1",
    "fields": [
        {"name": "schema_version", "type": "string"},
        {"name": "event_id", "type": "string"},
        {"name": "event_type", "type": "string"},
        {"name": "simulation", "type": "boolean"},
        {"name": "event_time", "type": "string"},
        {"name": "ano", "type": "long"},
        {"name": "id_municipio", "type": "string"},
        {"name": "rede", "type": "string"},
        {"name": "taxa_alfabetizacao", "type": "double"},
        {"name": "participacao", "type": ["null", "double"], "default": None},
        {"name": "producer", "type": "string"},
        {"name": "correlation_id", "type": "string"},
    ],
}


@dataclass(frozen=True, slots=True)
class AvroContractError(Exception):
    """Indica incompatibilidade estrutural ou semântica no evento Avro."""

    reason: str

    @override
    def __str__(self) -> str:
        """Retorna uma mensagem segura, sem conteúdo do payload."""
        return self.reason


def encode_event(record: AvroRecord) -> bytes:
    """Serializa um registro somente quando ele satisfaz o schema Avro."""
    stream = io.BytesIO()
    try:
        _fastavro.schemaless_writer(stream, _fastavro.parse_schema(SCHEMA), record, strict=True)
    except (TypeError, ValueError, KeyError) as error:
        raise AvroContractError(
            reason="registro incompatível com MunicipalLiteracyRateUpdatedV1"
        ) from error
    return stream.getvalue()


def decode_event(payload: bytes) -> MunicipalLiteracyRateUpdatedV1:
    """Converte bytes Avro em um evento semanticamente válido."""
    try:
        decoded = _fastavro.schemaless_reader(io.BytesIO(payload), _fastavro.parse_schema(SCHEMA))
        return MunicipalLiteracyRateUpdatedV1.model_validate(decoded)
    except (TypeError, ValueError, KeyError, EOFError, ValidationError) as error:
        raise AvroContractError(
            reason="payload Avro inválido ou semanticamente incompatível"
        ) from error
