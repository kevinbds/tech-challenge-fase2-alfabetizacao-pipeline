from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.errors import CostLimitExceededError
from alfabetizacao_pipeline.batch.fakes import (
    FakeBigQuery,
    InMemoryManifestStore,
    InMemoryObjectStore,
)
from alfabetizacao_pipeline.batch.models import BatchRequest, BatchRunContext, DryRunEstimate
from alfabetizacao_pipeline.batch.planner import plan_batch
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime, SystemClock
from alfabetizacao_pipeline.errors import ExitCode
from alfabetizacao_pipeline.schema_reference.builder import build_reference_file
from alfabetizacao_pipeline.types import OutputFormat

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
source_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
app.add_typer(source_app, name="source")


def _query(estimated_bytes: int) -> FakeBigQuery:
    return FakeBigQuery(estimate=DryRunEstimate(bytes_processed=estimated_bytes))


def _request(source: str, year: int, maximum_bytes_billed: int, dry_run: bool) -> BatchRequest:
    if source not in SOURCE_CATALOG:
        typer.echo('{"status":"invalid_request"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION)
    try:
        return BatchRequest(
            source=source,
            year=year,
            maximum_bytes_billed=maximum_bytes_billed,
            dry_run=dry_run,
        )
    except ValidationError as error:
        typer.echo('{"status":"invalid_request"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error


@source_app.command("inspect")
def inspect_source(
    source: Annotated[str, typer.Option("--source")],
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Inspect source location and schema through a no-cloud fixture adapter."""
    request = _request(source, 2024, 25 * 1024**3, dry_run=True)
    inspection = _query(0).inspect(request.source)
    typer.echo(inspection.model_dump_json())


@app.command("plan")
def plan(
    source: Annotated[str, typer.Option("--source")],
    year: Annotated[int, typer.Option("--year")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
    maximum_bytes_billed: Annotated[int, typer.Option("--maximum-bytes-billed")] = 25 * 1024**3,
    estimated_bytes: Annotated[int, typer.Option("--estimated-bytes")] = 1024**3,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Return a bounded dry-run plan and stable JSON exit contract."""
    request = _request(source, year, maximum_bytes_billed, dry_run)
    try:
        result = plan_batch(request, _query(estimated_bytes), InMemoryManifestStore())
    except CostLimitExceededError as error:
        typer.echo(
            (
                '{"status":"cost_limit_exceeded",'
                f'"estimated_bytes":{error.estimated_bytes},'
                f'"maximum_bytes_billed":{error.maximum_bytes_billed}'
                "}"
            ),
            err=True,
        )
        raise typer.Exit(code=ExitCode.COST_LIMIT_EXCEEDED) from error
    typer.echo(result.model_dump_json())


@app.command("run")
def run(
    source: Annotated[str, typer.Option("--source")],
    year: Annotated[int, typer.Option("--year")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Execute the state machine against isolated local fixture adapters."""
    request = _request(source, year, 25 * 1024**3, dry_run)
    query = _query(1024**3)
    if dry_run:
        typer.echo(plan_batch(request, query, InMemoryManifestStore()).model_dump_json())
        return
    manifests = InMemoryManifestStore()
    objects = InMemoryObjectStore()
    with TemporaryDirectory(prefix="alfabetizacao-batch-") as temp_directory:
        reference = Path(temp_directory) / "fixture.parquet"
        _ = build_reference_file(SOURCE_CATALOG[source], reference)
        objects.seed("gs://landing/fixture.parquet", reference.read_bytes())
        result = execute_batch(
            request,
            BatchRuntime(query=query, manifests=manifests, objects=objects, clock=SystemClock()),
            BatchRunContext(
                landing_prefix="gs://landing",
                bronze_prefix="gs://bronze",
                git_sha="local-fixture",
                image_digest="sha256:local-fixture",
            ),
        )
    typer.echo(result.model_dump_json())


if __name__ == "__main__":
    app()
