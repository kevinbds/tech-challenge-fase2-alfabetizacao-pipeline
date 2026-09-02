import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, override

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline.streaming.avro_codec import AvroContractError, AvroRecord, encode_event
from alfabetizacao_pipeline.streaming.avro_types import (
    DemoFixture,
    ReleaseContext,
    accepted_records_for_release,
)
from alfabetizacao_pipeline.streaming.beam_job import run_direct
from alfabetizacao_pipeline.streaming.envelope import MessageEnvelope
from alfabetizacao_pipeline.streaming.processor import process_messages

app = typer.Typer(add_completion=False, no_args_is_help=True)


@dataclass(frozen=True, slots=True)
class FixtureShapeError(TypeError):
    """Indica uma fixture sem as duas coleções contratuais."""

    path: Path

    @override
    def __str__(self) -> str:
        """Retorna apenas o caminho local, nunca o conteúdo da fixture."""
        return f"fixture {self.path} precisa conter accepted e schema_incompatible"


@dataclass(frozen=True, slots=True)
class DemoReport:
    """Contagens observáveis e latência da demonstração local."""

    raw_message_ids: int
    valid_event_ids: int
    duplicate_audit: int
    quarantine: int
    schema_rejected: int
    redeliveries_tolerated: int
    p95_latency_seconds: float
    runner: str = "DirectRunner"


def _load_fixture(path: Path) -> DemoFixture:
    try:
        return DemoFixture.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise FixtureShapeError(path=path) from error


def _write_jsonl(path: Path, rows: tuple[AvroRecord, ...]) -> None:
    content = "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows)
    _ = path.write_text(content, encoding="utf-8")


def run_demo(fixture: Path, output: Path, release: ReleaseContext) -> DemoReport:
    """Executa a fixture pelo DirectRunner e grava saídas determinísticas."""
    decoded = _load_fixture(fixture)
    accepted = accepted_records_for_release(decoded, release)
    output.mkdir(parents=True, exist_ok=True)
    envelopes = tuple(
        MessageEnvelope(
            message_id=f"message-{index:02d}",
            payload=encode_event(record),
            publish_time=release.base_time + timedelta(seconds=index),
            ingestion_time=release.base_time + timedelta(seconds=index, milliseconds=250),
        )
        for index, record in enumerate(accepted, start=1)
    )
    schema_rejected = 0
    try:
        _ = encode_event(decoded.schema_incompatible)
    except AvroContractError:
        schema_rejected = 1

    redelivery = envelopes[0]
    beam_input = tuple(
        json.dumps({"message_id": message.message_id}, sort_keys=True)
        for message in (*envelopes, redelivery)
    )
    run_direct(beam_input, output / "beam-raw")
    result = process_messages((*envelopes, redelivery))

    valid_rows = tuple(item.event.model_dump(mode="json") for item in result.valid)
    duplicate_rows = tuple(asdict(item) for item in result.duplicates)
    quarantine_rows = tuple(asdict(item) for item in result.quarantine)
    _write_jsonl(output / "valid.jsonl", valid_rows)
    _write_jsonl(output / "duplicate_audit.jsonl", duplicate_rows)
    _write_jsonl(output / "quarantine.jsonl", quarantine_rows)
    report = DemoReport(
        raw_message_ids=len(result.raw),
        valid_event_ids=len(result.valid),
        duplicate_audit=len(result.duplicates),
        quarantine=len(result.quarantine),
        schema_rejected=schema_rejected,
        redeliveries_tolerated=result.redelivery_count,
        p95_latency_seconds=result.p95_latency_seconds,
    )
    _ = (output / "report.json").write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


@app.command()
def main(
    fixture: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(file_okay=False)],
    year: Annotated[int, typer.Option(min=2000, max=2100)],
    output_format: Annotated[str, typer.Option("--format")] = "json",
    base_time: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Executa o subapp local e imprime somente o relatório agregado."""
    if output_format != "json":
        msg = "somente --format json é suportado"
        raise typer.BadParameter(msg)
    try:
        release = ReleaseContext(
            target_year=year,
            base_time=datetime.fromisoformat(base_time) if base_time else datetime.now(UTC),
        )
    except (ValidationError, ValueError) as error:
        message = "--base-time exige data/hora ISO 8601 em UTC"
        raise typer.BadParameter(message) from error
    report = run_demo(fixture, output, release)
    typer.echo(json.dumps(asdict(report), sort_keys=True))


if __name__ == "__main__":
    app()
