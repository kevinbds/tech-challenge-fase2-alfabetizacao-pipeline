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
    # Given a real Avro record and an in-memory publisher port
    publisher = PublisherFake()
    policy = PublishPolicy(timeout_seconds=7, retry_deadline_seconds=5)

    # When checked publication completes
    receipt = publish_checked(
        publisher, "projects/demo/topics/literacy", transport_record(), policy
    )

    # Then the port receives valid Avro and only safe correlation metadata
    assert publisher.calls == 1
    assert publisher.payload is not None
    assert decode_event(publisher.payload).id_municipio == "3550308"
    assert publisher.correlation_id == "safe-correlation"
    assert publisher.future.timeout == 7
    assert receipt.message_id == "pubsub-message-1"


def test_incompatible_publish_never_invokes_port() -> None:
    # Given an incompatible record and a publisher that records invocations
    publisher = PublisherFake()
    invalid = transport_record()
    del invalid["event_id"]

    # When checked publication validates the transport boundary
    with pytest.raises(AvroContractError):
        _ = publish_checked(publisher, "projects/demo/topics/literacy", invalid, PublishPolicy())

    # Then Pub/Sub was never called
    assert publisher.calls == 0


def test_google_adapter_applies_bounded_timeout_and_retry() -> None:
    # Given the narrow official-client surface and an explicit policy
    client = GoogleClientFake()
    adapter = GooglePubSubPublisher(client, PublishPolicy(timeout_seconds=9))

    # When the adapter publishes already validated bytes
    future = adapter.publish("projects/demo/topics/literacy", b"avro", "safe-correlation")

    # Then the policy and safe correlation field cross the SDK boundary
    assert future is client.future
    assert client.timeout == 9
    assert client.correlation_id == "safe-correlation"
