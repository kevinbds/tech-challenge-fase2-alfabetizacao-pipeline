from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import apache_beam as beam
from apache_beam.io.gcp.bigquery import BigQueryDisposition, WriteToBigQuery
from apache_beam.io.gcp.pubsub import PubsubMessage, ReadFromPubSub
from apache_beam.options.pipeline_options import PipelineOptions

from alfabetizacao_pipeline.streaming.avro_codec import encode_event
from alfabetizacao_pipeline.streaming.avro_types import DemoFixture
from alfabetizacao_pipeline.streaming.beam_routes import BeamEnvelope, RouteEventDoFn

STORAGE_METHODS: Final = frozenset({"STORAGE_WRITE_API", "STORAGE_API_AT_LEAST_ONCE"})


def _pubsub_envelope(message: PubsubMessage) -> BeamEnvelope:
    publish_time = message.publish_time or datetime.now(tz=UTC)
    message_id = message.message_id or "missing-message-id"
    return BeamEnvelope(
        message_id=message_id,
        payload=message.data,
        publish_time=publish_time,
        ingestion_time=datetime.now(tz=UTC),
    )


def _fixture_envelopes(path: Path) -> list[BeamEnvelope]:
    fixture = DemoFixture.model_validate_json(path.read_text(encoding="utf-8"))
    instant = datetime(2026, 8, 29, 12, tzinfo=UTC)
    return [
        BeamEnvelope(
            message_id=f"message-{index:02d}",
            payload=encode_event(record.as_avro_record()),
            publish_time=instant,
            ingestion_time=instant,
        )
        for index, record in enumerate(fixture.accepted, start=1)
    ]


def _json_line(row: dict[str, str | int | float | bool | None]) -> str:
    return json.dumps(row, sort_keys=True)


def run(argv: list[str] | None = None) -> None:
    """Execute a pipeline pelo launcher Flex ou pelo DirectRunner local."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_subscription")
    parser.add_argument("--valid_table")
    parser.add_argument("--quarantine_table")
    parser.add_argument("--write_method", default="STORAGE_API_AT_LEAST_ONCE")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--output_dir", type=Path)
    known, pipeline_args = parser.parse_known_args(argv)
    if known.write_method not in STORAGE_METHODS:
        parser.error("write_method precisa usar BigQuery Storage Write API")
    options = PipelineOptions(pipeline_args, streaming=True)

    with beam.Pipeline(options=options) as pipeline:
        if known.fixture is not None:
            incoming = pipeline | "Fixture" >> beam.Create(_fixture_envelopes(known.fixture))
        else:
            if not known.input_subscription:
                parser.error("input_subscription é obrigatório no modo Dataflow")
            incoming = (
                pipeline
                | "ReadPubSub"
                >> ReadFromPubSub(subscription=known.input_subscription, with_attributes=True)
                | "PubSubEnvelope" >> beam.Map(_pubsub_envelope)
            )
        routed = incoming | "ValidateAndRoute" >> beam.ParDo(RouteEventDoFn()).with_outputs(
            RouteEventDoFn.QUARANTINE, main=RouteEventDoFn.VALID
        )
        if known.fixture is not None:
            if known.output_dir is None:
                parser.error("output_dir é obrigatório no modo fixture")
            _ = (
                routed.valid
                | "ValidJson" >> beam.Map(_json_line)
                | "WriteValid" >> beam.io.WriteToText(str(known.output_dir / "valid"), num_shards=1)
            )
            _ = (
                routed.quarantine
                | "QuarantineJson" >> beam.Map(_json_line)
                | "WriteQuarantine"
                >> beam.io.WriteToText(str(known.output_dir / "quarantine"), num_shards=1)
            )
        else:
            if not known.valid_table or not known.quarantine_table:
                parser.error("valid_table e quarantine_table são obrigatórios no Dataflow")
            _ = routed.valid | "ValidToBigQuery" >> WriteToBigQuery(
                table=known.valid_table,
                method=known.write_method,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
            )
            _ = routed.quarantine | "QuarantineToBigQuery" >> WriteToBigQuery(
                table=known.quarantine_table,
                method=known.write_method,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
            )


if __name__ == "__main__":
    run()
