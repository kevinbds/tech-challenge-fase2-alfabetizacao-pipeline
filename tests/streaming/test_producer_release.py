from datetime import UTC, datetime, timedelta
from pathlib import Path

from alfabetizacao_pipeline.streaming import avro_codec, producer
from alfabetizacao_pipeline.streaming.avro_types import AvroTransportRecord, ReleaseContext
from alfabetizacao_pipeline.streaming.publisher import PublishFuture, PublishPolicy


class _CompletedFuture:
    def result(self, timeout: float | None = None) -> str:
        del timeout
        return "captured"


class _CapturePublisher:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def publish(self, topic: str, payload: bytes, correlation_id: str) -> PublishFuture:
        del topic, correlation_id
        self.payloads.append(payload)
        return _CompletedFuture()


def test_producer_overrides_release_year_and_event_times_in_fixture_order() -> None:
    base_time = datetime(2031, 2, 3, 4, 5, 6, tzinfo=UTC)
    request = producer.ProducerRequest(
        mode=producer.ProducerMode.LOCAL,
        topic="projects/demo/topics/literacy",
        fixture_path=Path("contracts/events/fixtures/demo.json"),
        release=ReleaseContext(
            target_year=2031,
            base_time=base_time,
            correlation_id="release-2031",
        ),
    )
    publisher = _CapturePublisher()

    report = producer.run_producer(request, PublishPolicy(), publisher)
    events = tuple(
        AvroTransportRecord.model_validate(avro_codec.decode_transport_record(payload))
        for payload in publisher.payloads
    )

    assert report.published == 10
    assert report.schema_rejected == 1
    assert [event.ano for event in events] == [2031] * 10
    assert [event.event_time for event in events] == [
        (base_time + timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
        for index in range(1, 11)
    ]
    assert events[0].event_id == events[8].event_id
    assert events[0].taxa_alfabetizacao == 91.1
    assert events[8].taxa_alfabetizacao == 92.1
    assert [event.correlation_id for event in events] == ["release-2031"] * 10
