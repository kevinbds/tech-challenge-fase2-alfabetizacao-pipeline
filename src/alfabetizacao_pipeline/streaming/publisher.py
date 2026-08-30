from dataclasses import dataclass
from typing import Protocol

from google.api_core.retry import Retry

from alfabetizacao_pipeline.streaming.avro_codec import AvroRecord, encode_event


class PublishFuture(Protocol):
    """Resultado aguardável de uma publicação."""

    def result(self, timeout: float | None = None) -> str:
        """Aguarda o aceite e retorna o message ID do Pub/Sub."""
        ...


class Publisher(Protocol):
    """Porta mínima para publicar bytes já validados."""

    def publish(self, topic: str, payload: bytes, correlation_id: str) -> PublishFuture:
        """Envia um payload já validado para um tópico explícito."""
        ...


class GooglePublisherClient(Protocol):
    """Superfície usada do cliente oficial do Pub/Sub."""

    def publish(
        self,
        topic: str,
        data: bytes,
        *,
        correlation_id: str,
        retry: Retry,
        timeout: float,
    ) -> PublishFuture:
        """Publica com os limites fornecidos pelo adaptador."""
        ...


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    """Identificadores não sensíveis retornados após a publicação."""

    message_id: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class PublishPolicy:
    """Limites explícitos de timeout e retry do producer."""

    timeout_seconds: float = 30.0
    retry_deadline_seconds: float = 20.0


class GooglePubSubPublisher:
    """Adaptador síncrono do PublisherClient oficial."""

    _client: GooglePublisherClient
    _policy: PublishPolicy

    def __init__(self, client: GooglePublisherClient, policy: PublishPolicy) -> None:
        """Configura um publisher sem manter conteúdo do evento."""
        self._client = client
        self._policy = policy

    def publish(self, topic: str, payload: bytes, correlation_id: str) -> PublishFuture:
        """Publica bytes validados com retry e timeout limitados."""
        return self._client.publish(
            topic,
            payload,
            correlation_id=correlation_id,
            retry=Retry(deadline=self._policy.retry_deadline_seconds),
            timeout=self._policy.timeout_seconds,
        )


def publish_checked(
    publisher: Publisher,
    topic: str,
    record: AvroRecord,
    policy: PublishPolicy,
) -> PublishReceipt:
    """Valida Avro antes de invocar a porta de publicação."""
    payload = encode_event(record)
    correlation_id = str(record["correlation_id"])
    future = publisher.publish(topic, payload, correlation_id)
    return PublishReceipt(
        message_id=future.result(timeout=policy.timeout_seconds),
        correlation_id=correlation_id,
    )
