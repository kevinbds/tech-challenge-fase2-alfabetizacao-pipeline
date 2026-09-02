from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Self, TypedDict, Unpack

from apache_beam.io.gcp.bigquery import BigQueryDisposition, WriteToBigQuery
from containers.dataflow import beam_entrypoint

from alfabetizacao_pipeline.streaming import beam_sinks

STORAGE_SCHEMA_PROGRAM = """
from pathlib import Path
from apache_beam.coders import RowCoder
from apache_beam.io.gcp.bigquery import bigquery_tools
from apache_beam.typehints.row_type import RowTypeConstraint
from apache_beam.typehints.schemas import schema_from_element_type
from containers.dataflow import beam_entrypoint
from alfabetizacao_pipeline.streaming import beam_sinks
from alfabetizacao_pipeline.streaming.beam_routes import quarantine_row, staged_event_row

envelopes = beam_entrypoint.fixture_envelopes(Path("contracts/events/fixtures/demo.json"))
rows = (
    (
        beam_sinks.valid_storage_row(staged_event_row(envelopes[0])),
        beam_sinks.VALID_TABLE_SCHEMA,
    ),
    (
        beam_sinks.quarantine_storage_row(quarantine_row(envelopes[-1])),
        beam_sinks.QUARANTINE_TABLE_SCHEMA,
    ),
)
for row, table_schema in rows:
    type_hint = RowTypeConstraint.from_fields(
        bigquery_tools.get_beam_typehints_from_tableschema(table_schema)
    )
    beam_row = bigquery_tools.beam_row_from_dict(row, table_schema)
    encoded = RowCoder(schema_from_element_type(type_hint.user_type)).encode(beam_row)
    assert encoded
"""

if TYPE_CHECKING:
    from types import TracebackType

    import pytest
    from apache_beam.options.pipeline_options import PipelineOptions

    from alfabetizacao_pipeline.streaming.beam_routes import RouteEventDoFn


class _Transform:
    def __init__(self) -> None:
        self.label: str = ""

    def __rrshift__(self, _: str) -> Self:
        self.label = _
        return self

    def with_outputs(self, *_: str, **_kwargs: str) -> Self:
        return self


class _PCollection:
    @property
    def valid(self) -> Self:
        return self

    @property
    def quarantine(self) -> Self:
        return self


class _TableField(TypedDict):
    name: str
    type: str
    mode: str


class _TableSchema(TypedDict):
    fields: list[_TableField]


class _WriteToBigQueryKwargs(TypedDict):
    table: str
    schema: _TableSchema
    method: WriteToBigQuery.Method
    use_at_least_once: bool
    create_disposition: BigQueryDisposition
    write_disposition: BigQueryDisposition


class _Pipeline:
    def __init__(self) -> None:
        self.context_entries: int = 0
        self.run_calls: int = 0
        self.wait_calls: int = 0

    def __enter__(self) -> Self:
        self.context_entries += 1
        return self

    def __exit__(
        self,
        _: type[BaseException] | None,
        __: BaseException | None,
        ___: TracebackType | None,
    ) -> None:
        self.run().wait_until_finish()

    def run(self) -> Self:
        self.run_calls += 1
        return self

    def wait_until_finish(self) -> None:
        self.wait_calls += 1


class _PipelineFactory:
    def __init__(self) -> None:
        self.pipeline: _Pipeline = _Pipeline()

    def __call__(self, *, options: PipelineOptions) -> _Pipeline:
        _ = options
        return self.pipeline


def test_flex_launcher_returns_after_submitting_pipeline_without_context_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _PipelineFactory()
    transform = _Transform()

    def par_do(_: RouteEventDoFn) -> _Transform:
        return transform

    def read_from_pubsub(*, subscription: str, with_attributes: bool) -> _Transform:
        assert subscription == "projects/example/subscriptions/alfabetizacao-events"
        assert with_attributes is True
        return transform

    sink_calls: list[_WriteToBigQueryKwargs] = []

    def write_to_bigquery(**kwargs: Unpack[_WriteToBigQueryKwargs]) -> _Transform:
        sink_calls.append(kwargs)
        return transform

    def create_collection(
        pipeline: _Pipeline,
        label: str,
        collection_transform: _Transform,
    ) -> _PCollection:
        _ = pipeline, label, collection_transform
        return _PCollection()

    def apply_collection_transform(
        collection: _PCollection,
        label: str,
        collection_transform: _Transform,
    ) -> _PCollection:
        _ = collection, label, collection_transform
        return _PCollection()

    def route_collections(
        collection: _PCollection,
        route_transform: _Transform,
    ) -> _PCollection:
        _ = collection, route_transform
        return _PCollection()

    def write_collection(
        collection: _PCollection,
        label: str,
        sink_transform: _Transform,
    ) -> None:
        _ = collection, label, sink_transform

    monkeypatch.setattr("containers.dataflow.beam_entrypoint.beam.Pipeline", factory)
    monkeypatch.setattr("containers.dataflow.beam_entrypoint.beam.ParDo", par_do)
    monkeypatch.setattr(beam_entrypoint, "ReadFromPubSub", read_from_pubsub)
    monkeypatch.setattr(beam_entrypoint, "WriteToBigQuery", write_to_bigquery)
    monkeypatch.setattr("containers.dataflow.beam_entrypoint._create_collection", create_collection)
    monkeypatch.setattr(
        "containers.dataflow.beam_entrypoint._apply_collection_transform",
        apply_collection_transform,
    )
    monkeypatch.setattr("containers.dataflow.beam_entrypoint._route_collections", route_collections)
    monkeypatch.setattr("containers.dataflow.beam_entrypoint._write_collection", write_collection)

    beam_entrypoint.run(
        [
            "--input_subscription",
            "projects/example/subscriptions/alfabetizacao-events",
            "--valid_table",
            "example:silver.municipal_rate_stream",
            "--quarantine_table",
            "example:quarantine.stream_events",
        ]
    )

    assert factory.pipeline.context_entries == 0
    assert factory.pipeline.run_calls == 1
    assert factory.pipeline.wait_calls == 0
    assert len(sink_calls) == 2
    assert {call["table"] for call in sink_calls} == {
        "example:silver.municipal_rate_stream",
        "example:quarantine.stream_events",
    }
    assert {call["method"] for call in sink_calls} == {WriteToBigQuery.Method.STORAGE_WRITE_API}
    assert all(call["use_at_least_once"] is True for call in sink_calls)
    assert all(call["schema"] for call in sink_calls)
    assert beam_sinks.VALID_TABLE_SCHEMA["fields"][-2] == {
        "name": "correlation_id",
        "type": "STRING",
        "mode": "REQUIRED",
    }
    assert beam_sinks.QUARANTINE_TABLE_SCHEMA["fields"][-1] == {
        "name": "correlation_id",
        "type": "STRING",
        "mode": "NULLABLE",
    }
    assert beam_sinks.QUARANTINE_TABLE_SCHEMA["fields"][-2] == {
        "name": "event_fingerprint",
        "type": "STRING",
        "mode": "REQUIRED",
    }


def test_sink_rows_encode_with_the_storage_write_api_schemas() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", STORAGE_SCHEMA_PROGRAM],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
