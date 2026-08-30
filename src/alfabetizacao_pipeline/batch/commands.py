import os
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
from alfabetizacao_pipeline.batch.models import (
    BatchRequest,
    BatchRunContext,
    DeploymentProvenance,
    DryRunEstimate,
)
from alfabetizacao_pipeline.batch.planner import plan_batch
from alfabetizacao_pipeline.batch.production import build_production_composition
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime, SystemClock
from alfabetizacao_pipeline.config import AppSettings
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


def _deployment_provenance() -> DeploymentProvenance:
    try:
        return DeploymentProvenance.model_validate(
            {
                "git_sha": os.environ.get("ALFABETIZACAO_GIT_SHA"),
                "image_digest": os.environ.get("ALFABETIZACAO_IMAGE_DIGEST"),
            }
        )
    except ValidationError as error:
        typer.echo('{"status":"invalid_deployment_provenance"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error


@source_app.command("inspect")
def inspect_source(
    source: Annotated[str, typer.Option("--source")],
    demo: Annotated[bool, typer.Option("--demo")] = False,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Inspect runtime source metadata; fixtures require explicit demo mode."""
    request = _request(source, 2024, 25 * 1024**3, dry_run=True)
    query = (
        _query(0)
        if demo
        else build_production_composition(
            source,
            AppSettings(),
            git_sha="inspection-only",
            image_digest="inspection-only",
        ).runtime.query
    )
    inspection = query.inspect(request.source)
    typer.echo(inspection.model_dump_json())


@app.command("plan")
def plan(
    source: Annotated[str, typer.Option("--source")],
    year: Annotated[int, typer.Option("--year")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
    maximum_bytes_billed: Annotated[int, typer.Option("--maximum-bytes-billed")] = 25 * 1024**3,
    demo_estimated_bytes: Annotated[
        int | None,
        typer.Option("--demo-estimated-bytes"),
    ] = None,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Return a bounded dry-run plan and stable JSON exit contract."""
    request = _request(source, year, maximum_bytes_billed, dry_run)
    try:
        if demo_estimated_bytes is not None:
            query = _query(demo_estimated_bytes)
            manifests = InMemoryManifestStore()
        else:
            composition = build_production_composition(
                source,
                AppSettings(),
                git_sha="plan-only",
                image_digest="plan-only",
            )
            query = composition.runtime.query
            manifests = composition.runtime.manifests
        result = plan_batch(request, query, manifests)
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
    demo: Annotated[bool, typer.Option("--demo")] = False,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Run production adapters; local fixtures require explicit demo mode."""
    request = _request(source, year, 25 * 1024**3, dry_run)
    if not demo:
        provenance = _deployment_provenance()
        composition = build_production_composition(
            source,
            AppSettings(),
            git_sha=provenance.git_sha,
            image_digest=provenance.image_digest,
        )
        if dry_run:
            plan_result = plan_batch(
                request,
                composition.runtime.query,
                composition.runtime.manifests,
            )
            typer.echo(plan_result.model_dump_json())
            return
        typer.echo(
            execute_batch(request, composition.runtime, composition.context).model_dump_json()
        )
        return
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
