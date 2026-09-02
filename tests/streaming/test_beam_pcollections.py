import subprocess
import sys
from pathlib import Path

TEST_PIPELINE_PROGRAM = """
from datetime import UTC, datetime
from pathlib import Path
from apache_beam import Create, ParDo
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to
from alfabetizacao_pipeline.streaming.avro_types import DemoFixture
from alfabetizacao_pipeline.streaming.avro_codec import encode_event
from alfabetizacao_pipeline.streaming.beam_routes import BeamEnvelope, RouteEventDoFn

fixture = DemoFixture.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
now = datetime(2026, 8, 29, 12, tzinfo=UTC)
envelopes = [
    BeamEnvelope(
        message_id=f"message-{index:02d}",
        payload=encode_event(record.as_avro_record()),
        publish_time=now,
        ingestion_time=now,
    )
    for index, record in enumerate(fixture.accepted, start=1)
]
with TestPipeline() as pipeline:
    routed = pipeline | Create(envelopes) | ParDo(RouteEventDoFn()).with_outputs(
        RouteEventDoFn.QUARANTINE, main=RouteEventDoFn.VALID
    )
    assert_that(routed.valid | "ValidIds" >> beam.Map(lambda row: row["message_id"]),
                equal_to([f"message-{index:02d}" for index in range(1, 10)]), label="Valid")
    assert_that(routed.quarantine | "QuarantineIds" >> beam.Map(lambda row: row["message_id"]),
                equal_to(["message-10"]), label="Quarantine")
"""


def test_beam_routes_avro_and_semantic_validation_inside_real_pcollections() -> None:
    fixture = Path("contracts/events/fixtures/demo.json")

    program = "import sys\nimport apache_beam as beam\n" + TEST_PIPELINE_PROGRAM
    completed = subprocess.run(
        [sys.executable, "-c", program, str(fixture)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
