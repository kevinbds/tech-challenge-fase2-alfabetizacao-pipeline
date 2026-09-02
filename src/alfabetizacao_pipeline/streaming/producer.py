import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum, unique
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Protocol, assert_never

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, encode_event
from alfabetizacao_pipeline.streaming.avro_types import (
    DemoFixture,
    ReleaseContext,
    accepted_records_for_release,
)
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
    target_year: int
    base_time: str


@dataclass(frozen=True, slots=True)
class ProducerRequest:
    """Entrada já validada para publicar uma release da fixture."""

    mode: ProducerMode
    topic: str
    fixture_path: Path
    release: ReleaseContext


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
    request: ProducerRequest,
    policy: PublishPolicy,
    publisher: Publisher,
) -> ProducerReport:
    """Publica dez registros compatíveis e rejeita o incompatível antes da porta."""
    fixture = DemoFixture.model_validate_json(request.fixture_path.read_text(encoding="utf-8"))
    published = 0
    for avro_record in accepted_records_for_release(fixture, request.release):
        _ = publish_checked(publisher, request.topic, avro_record, policy)
        published += 1
    rejected = 0
    try:
        _ = encode_event(fixture.schema_incompatible)
    except AvroContractError:
        rejected = 1
    return ProducerReport(
        published=published,
        schema_rejected=rejected,
        mode=request.mode,
        target_year=request.release.target_year,
        base_time=request.release.base_time.isoformat().replace("+00:00", "Z"),
    )


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    mode: Annotated[ProducerMode, typer.Option()],
    topic: Annotated[str, typer.Option(envvar="PUBSUB_TOPIC")],
    fixture: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    report: Annotated[Path, typer.Option(dir_okay=False)],
    year: Annotated[int, typer.Option(min=2000, max=2100)],
) -> None:
    """Executa o producer em Pub/Sub real ou no modo local explicitamente pedido."""
    try:
        release = ReleaseContext(
            target_year=year,
            base_time=datetime.now(UTC),
            correlation_id=os.getenv("CORRELATION_ID"),
        )
    except ValidationError as error:
        message = "CORRELATION_ID precisa ter entre 1 e 128 caracteres"
        raise typer.BadParameter(message) from error
    policy = PublishPolicy()
    request = ProducerRequest(
        mode=mode,
        topic=topic,
        fixture_path=fixture,
        release=release,
    )
    result = run_producer(request, policy, _publisher(mode, policy))
    _ = report.write_text(json.dumps(asdict(result), sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"published={result.published} schema_rejected={result.schema_rejected}")


if __name__ == "__main__":
    app()
