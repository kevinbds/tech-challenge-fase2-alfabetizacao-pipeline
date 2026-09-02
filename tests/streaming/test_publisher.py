import pytest
from google.api_core.retry import Retry

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, AvroRecord, decode_event
from alfabetizacao_pipeline.streaming.publisher import (
    GooglePubSubPublisher,
    PublishFuture,
    PublishPolicy,
    publish_checked,
)


class FutureFake:
    timeout: float | None = None

    def result(self, timeout: float | None = None) -> str:
        self.timeout = timeout
        return "pubsub-message-1"


class PublisherFake:
    calls: int
    payload: bytes | None
    correlation_id: str | None
    future: FutureFake

    def __init__(self) -> None:
        self.calls = 0
        self.payload = None
        self.correlation_id = None
        self.future = FutureFake()

    def publish(self, topic: str, payload: bytes, correlation_id: str) -> PublishFuture:
        self.calls += 1
        self.payload = payload
        self.correlation_id = correlation_id
        assert topic == "projects/demo/topics/literacy"
        return self.future


class GoogleClientFake:
    timeout: float | None
    correlation_id: str | None
    future: FutureFake

    def __init__(self) -> None:
        self.timeout = None
        self.correlation_id = None
        self.future = FutureFake()

    def publish(
        self,
        topic: str,
        data: bytes,
        *,
        correlation_id: str,
        retry: Retry,
        timeout: float,
    ) -> PublishFuture:
        assert topic == "projects/demo/topics/literacy"
        assert len(data) > 0
        assert isinstance(retry, Retry)
        self.timeout = timeout
        self.correlation_id = correlation_id
        return self.future


def transport_record() -> AvroRecord:
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
        "participacao": None,
        "producer": "fixture-v1",
        "correlation_id": "safe-correlation",
    }


def test_checked_publish_serializes_before_invoking_port() -> None:
    publisher = PublisherFake()
    policy = PublishPolicy(timeout_seconds=7, retry_deadline_seconds=5)

    receipt = publish_checked(
        publisher, "projects/demo/topics/literacy", transport_record(), policy
    )

    assert publisher.calls == 1
    assert publisher.payload is not None
    assert decode_event(publisher.payload).id_municipio == "3550308"
    assert publisher.correlation_id == "safe-correlation"
    assert publisher.future.timeout == 7
    assert receipt.message_id == "pubsub-message-1"


def test_incompatible_publish_never_invokes_port() -> None:
    publisher = PublisherFake()
    invalid = transport_record()
    del invalid["event_id"]

    with pytest.raises(AvroContractError):
        _ = publish_checked(publisher, "projects/demo/topics/literacy", invalid, PublishPolicy())

    assert publisher.calls == 0


def test_google_adapter_applies_bounded_timeout_and_retry() -> None:
    client = GoogleClientFake()
    adapter = GooglePubSubPublisher(client, PublishPolicy(timeout_seconds=9))

    future = adapter.publish("projects/demo/topics/literacy", b"avro", "safe-correlation")

    assert future is client.future
    assert client.timeout == 9
    assert client.correlation_id == "safe-correlation"
