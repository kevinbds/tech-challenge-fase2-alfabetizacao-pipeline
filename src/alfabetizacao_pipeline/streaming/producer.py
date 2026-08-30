import json
from dataclasses import asdict, dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Protocol, assert_never

import typer

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, encode_event
from alfabetizacao_pipeline.streaming.avro_types import DemoFixture
from alfabetizacao_pipeline.streaming.publisher import (
    GooglePublisherClient,
    GooglePubSubPublisher,
    Publisher,
    PublishFuture,
    PublishPolicy,
    publish_checked,
)

if TYPE_CHECKING:

    class _PubSubModule(Protocol):
        def PublisherClient(self) -> GooglePublisherClient: ...  # noqa: N802

    _pubsub_v1: _PubSubModule
else:
    from google.cloud import pubsub_v1 as _pubsub_v1


@unique
class ProducerMode(StrEnum):
    """Destino explicitamente selecionado para a fixture."""

    LOCAL = "local"
    PUBSUB = "pubsub"


@dataclass(frozen=True, slots=True)
class ProducerReport:
    """Contagens não sensíveis da execução do producer."""

    published: int
    schema_rejected: int
    mode: str


@dataclass(frozen=True, slots=True)
class _LocalFuture:
    message_id: str

    def result(self, timeout: float | None = None) -> str:
        _ = timeout
        return self.message_id


class _LocalPublisher:
    def __init__(self) -> None:
        self.published: int = 0

    def publish(self, topic: str, payload: bytes, correlation_id: str) -> PublishFuture:
        del topic, payload, correlation_id
        self.published += 1
        return _LocalFuture(message_id=f"local-{self.published:02d}")


def _publisher(mode: ProducerMode, policy: PublishPolicy) -> Publisher:
    match mode:
        case ProducerMode.LOCAL:
            return _LocalPublisher()
        case ProducerMode.PUBSUB:
            return GooglePubSubPublisher(_pubsub_v1.PublisherClient(), policy)
        case _ as unreachable if not TYPE_CHECKING:
            assert_never(unreachable)


def run_producer(
    mode: ProducerMode,
    topic: str,
    fixture_path: Path,
    policy: PublishPolicy,
    correlation_id: str | None = None,
) -> ProducerReport:
    """Publica dez registros compatíveis e rejeita o incompatível antes da porta."""
    fixture = DemoFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    publisher = _publisher(mode, policy)
    published = 0
    for record in fixture.accepted:
        avro_record = record.as_avro_record()
        if correlation_id is not None:
            avro_record["correlation_id"] = correlation_id
        _ = publish_checked(publisher, topic, avro_record, policy)
        published += 1
    rejected = 0
    try:
        _ = encode_event(fixture.schema_incompatible)
    except AvroContractError:
        rejected = 1
    return ProducerReport(published=published, schema_rejected=rejected, mode=mode)


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    mode: Annotated[ProducerMode, typer.Option()],
    topic: Annotated[str, typer.Option()],
    fixture: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    report: Annotated[Path, typer.Option(dir_okay=False)],
    correlation_id: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Executa o producer em Pub/Sub real ou no modo local explicitamente pedido."""
    result = run_producer(mode, topic, fixture, PublishPolicy(), correlation_id)
    _ = report.write_text(json.dumps(asdict(result), sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"published={result.published} schema_rejected={result.schema_rejected}")


if __name__ == "__main__":
    app()
