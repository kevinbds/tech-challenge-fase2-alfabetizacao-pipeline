from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, overload, override, runtime_checkable

import apache_beam as beam
from apache_beam.io.gcp.bigquery import BigQueryDisposition, WriteToBigQuery
from apache_beam.io.gcp.pubsub import ReadFromPubSub
from apache_beam.io.textio import WriteToText
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.utils.timestamp import Timestamp

from alfabetizacao_pipeline.streaming.avro_codec import encode_event
from alfabetizacao_pipeline.streaming.avro_types import DemoFixture
from alfabetizacao_pipeline.streaming.beam_routes import (
    BeamEnvelope,
    QuarantineRow,
    RouteEventDoFn,
    StagedEventRow,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    apply_collection_transform as _apply_collection_transform,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    create_collection as _create_collection,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    create_transform as _create_transform,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    map_transform as _map_transform,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    wait_for_result as _wait_for_result,
)
from alfabetizacao_pipeline.streaming.beam_runtime import (
    write_collection as _write_collection,
)
from alfabetizacao_pipeline.streaming.beam_sinks import (
    QUARANTINE_TABLE_SCHEMA,
    VALID_TABLE_SCHEMA,
    QuarantineStorageRow,
    ValidStorageRow,
    quarantine_storage_row,
    valid_storage_row,
)

if TYPE_CHECKING:
    from apache_beam.pvalue import PBegin, PCollection, PDone
    from apache_beam.transforms.ptransform import PTransform


STORAGE_WRITE_METHOD: Final = WriteToBigQuery.Method.STORAGE_WRITE_API


class _PubsubMessageView(Protocol):
    @property
    def data(self) -> bytes: ...

    @property
    def attributes(self) -> dict[str, str]: ...

    @property
    def message_id(self) -> str | None: ...

    @property
    def publish_time(self) -> datetime | None: ...


class _JsonDefaultValue(Protocol):
    @override
    def __str__(self) -> str: ...


class _BeamTransformError(TypeError): ...


class _RunNamespace(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.input_subscription: str | None = None
        self.valid_table: str | None = None
        self.quarantine_table: str | None = None
        self.fixture: Path | None = None
        self.output_dir: Path | None = None


@dataclass(frozen=True, slots=True)
class _RoutedCollections:
    valid: PCollection[StagedEventRow]
    quarantine: PCollection[QuarantineRow]


@runtime_checkable
class _NamedOutputs(Protocol):
    @overload
    def __getitem__(self, tag: Literal["valid"]) -> PCollection[StagedEventRow]: ...

    @overload
    def __getitem__(self, tag: Literal["quarantine"]) -> PCollection[QuarantineRow]: ...


@runtime_checkable
class _MultiOutputTransform(Protocol):
    def with_outputs(
        self, *tags: str, main: str
    ) -> PTransform[PCollection[BeamEnvelope], _NamedOutputs]: ...


def _route_collections(
    source: PCollection[BeamEnvelope],
    transform: PTransform[PCollection[BeamEnvelope], _NamedOutputs],
) -> _RoutedCollections:
    result = source | "ValidateAndRoute" >> transform
    if not isinstance(result, _NamedOutputs):
        raise _BeamTransformError
    return _RoutedCollections(valid=result["valid"], quarantine=result["quarantine"])


def _named_route_transform(
    transform: _MultiOutputTransform,
) -> PTransform[PCollection[BeamEnvelope], _NamedOutputs]:
    return transform.with_outputs(RouteEventDoFn.QUARANTINE, main=RouteEventDoFn.VALID)


def pubsub_envelope(message: _PubsubMessageView) -> BeamEnvelope:
    """Adapt one attributed Pub/Sub message to the routing boundary."""
    return BeamEnvelope(
        message_id=message.message_id or "missing-message-id",
        payload=message.data,
        publish_time=message.publish_time or datetime.now(tz=UTC),
        ingestion_time=datetime.now(tz=UTC),
        correlation_id=message.attributes.get("correlation_id"),
    )


def fixture_envelopes(path: Path) -> list[BeamEnvelope]:
    """Encode the deterministic demo fixture as Beam input envelopes."""
    fixture = DemoFixture.model_validate_json(path.read_text(encoding="utf-8"))
    instant = datetime(2026, 8, 29, 12, tzinfo=UTC)
    return [
        BeamEnvelope(
            message_id=f"message-{index:02d}",
            payload=encode_event(record.as_avro_record()),
            publish_time=instant,
            ingestion_time=instant,
            correlation_id=record.correlation_id,
        )
        for index, record in enumerate(fixture.accepted, start=1)
    ]


def _json_default(value: _JsonDefaultValue) -> str:
    if isinstance(value, Timestamp):
        return value.to_utc_datetime().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    message = f"{type(value).__name__} não pode ser serializado como JSON"
    raise TypeError(message)


def _json_line(row: StagedEventRow | QuarantineRow) -> str:
    return json.dumps(dict(row), default=_json_default, sort_keys=True)


def run(argv: list[str] | None = None) -> None:
    """Submit Dataflow work, waiting only for local fixture execution."""
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--input_subscription")
    _ = parser.add_argument("--valid_table")
    _ = parser.add_argument("--quarantine_table")
    _ = parser.add_argument("--fixture", type=Path)
    _ = parser.add_argument("--output_dir", type=Path)
    known = _RunNamespace()
    _, pipeline_args = parser.parse_known_args(argv, namespace=known)
    options = PipelineOptions(pipeline_args, streaming=True)

    pipeline = beam.Pipeline(options=options)
    if known.fixture is not None:
        incoming = _create_collection(
            pipeline,
            "Fixture",
            _create_transform(fixture_envelopes(known.fixture)),
        )
    else:
        if not known.input_subscription:
            parser.error("input_subscription é obrigatório no modo Dataflow")
        pubsub_transform: PTransform[PBegin, PCollection[_PubsubMessageView]] = ReadFromPubSub(
            subscription=known.input_subscription,
            with_attributes=True,
        )
        pubsub_messages: PCollection[_PubsubMessageView] = _create_collection(
            pipeline, "ReadPubSub", pubsub_transform
        )
        incoming = _apply_collection_transform(
            pubsub_messages,
            "PubSubEnvelope",
            _map_transform(pubsub_envelope),
        )
    route_transform = _named_route_transform(beam.ParDo(RouteEventDoFn()))
    routed = _route_collections(incoming, route_transform)
    if known.fixture is not None:
        if known.output_dir is None:
            parser.error("output_dir é obrigatório no modo fixture")
        valid_json = _apply_collection_transform(
            routed.valid, "ValidJson", _map_transform(_json_line)
        )
        quarantine_json = _apply_collection_transform(
            routed.quarantine, "QuarantineJson", _map_transform(_json_line)
        )
        valid_text: PTransform[PCollection[str], PDone] = WriteToText(
            str(known.output_dir / "valid"), num_shards=1
        )
        quarantine_text: PTransform[PCollection[str], PDone] = WriteToText(
            str(known.output_dir / "quarantine"), num_shards=1
        )
        _ = _write_collection(valid_json, "WriteValid", valid_text)
        _ = _write_collection(quarantine_json, "WriteQuarantine", quarantine_text)
    else:
        if not known.valid_table or not known.quarantine_table:
            parser.error("valid_table e quarantine_table são obrigatórios no Dataflow")
        valid_rows = _apply_collection_transform(
            routed.valid, "ValidStorageTypes", _map_transform(valid_storage_row)
        )
        quarantine_rows = _apply_collection_transform(
            routed.quarantine,
            "QuarantineStorageTypes",
            _map_transform(quarantine_storage_row),
        )
        valid_sink: PTransform[PCollection[ValidStorageRow], PDone] = WriteToBigQuery(
            table=known.valid_table,
            schema=VALID_TABLE_SCHEMA,
            method=STORAGE_WRITE_METHOD,
            use_at_least_once=True,
            create_disposition=BigQueryDisposition.CREATE_NEVER,
            write_disposition=BigQueryDisposition.WRITE_APPEND,
        )
        quarantine_sink: PTransform[PCollection[QuarantineStorageRow], PDone] = WriteToBigQuery(
            table=known.quarantine_table,
            schema=QUARANTINE_TABLE_SCHEMA,
            method=STORAGE_WRITE_METHOD,
            use_at_least_once=True,
            create_disposition=BigQueryDisposition.CREATE_NEVER,
            write_disposition=BigQueryDisposition.WRITE_APPEND,
        )
        _ = _write_collection(valid_rows, "ValidToBigQuery", valid_sink)
        _ = _write_collection(quarantine_rows, "QuarantineToBigQuery", quarantine_sink)
    result = pipeline.run()
    if known.fixture is not None:
        _wait_for_result(result)


if __name__ == "__main__":
    run()
