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
from alfabetizacao_pipeline.batch.planner import estimate_batch
from alfabetizacao_pipeline.batch.production import (
    build_production_composition,
    build_production_query,
)
from alfabetizacao_pipeline.batch.release_bigquery import BigQueryReleaseStore
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution
from alfabetizacao_pipeline.batch.runner import execute_batch
from alfabetizacao_pipeline.batch.runtime import BatchRuntime, SystemClock
from alfabetizacao_pipeline.config import AppSettings
from alfabetizacao_pipeline.errors import ExitCode
from alfabetizacao_pipeline.schema_reference.builder import build_demo_file
from alfabetizacao_pipeline.types import OutputFormat

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
source_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
release_app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
app.add_typer(source_app, name="source")
app.add_typer(release_app, name="release")


def _query(estimated_bytes: int, *, snapshot_row_count: int = 0) -> FakeBigQuery:
    return FakeBigQuery(
        estimate=DryRunEstimate(bytes_processed=estimated_bytes),
        snapshot_row_count=snapshot_row_count,
    )


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


def _maximum_bytes_billed(settings: AppSettings, requested: int | None) -> int:
    if requested is None:
        return settings.max_bytes_billed
    if requested > settings.max_bytes_billed:
        typer.echo('{"status":"invalid_request"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION)
    return requested


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


def _release_execution(release_id: str, year: int) -> ReleaseExecution:
    try:
        return ReleaseExecution(release_id=release_id, year=year)
    except ValidationError as error:
        typer.echo('{"status":"invalid_release_execution"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error


def _release_store(settings: AppSettings) -> BigQueryReleaseStore:
    return BigQueryReleaseStore(
        settings.gcp_project_id,
        settings.bigquery_location,
        settings.max_bytes_billed,
    )


@release_app.command("begin")
def begin_release(
    release_id: Annotated[str, typer.Option("--release-id")],
    year: Annotated[int, typer.Option("--year")],
) -> None:
    """Open one six-source release."""
    execution = _release_execution(release_id, year)
    _release_store(AppSettings()).begin(execution)
    typer.echo(execution.model_dump_json())


@release_app.command("complete")
def complete_release(
    release_id: Annotated[str, typer.Option("--release-id")],
    year: Annotated[int, typer.Option("--year")],
) -> None:
    """Freeze a release only after all catalog sources are non-empty."""
    execution = _release_execution(release_id, year)
    _release_store(AppSettings()).complete(execution)
    typer.echo(execution.model_dump_json())


@release_app.command("fail")
def fail_release(
    release_id: Annotated[str, typer.Option("--release-id")],
    year: Annotated[int, typer.Option("--year")],
) -> None:
    """Mark a candidate failed without moving the active pointer."""
    execution = _release_execution(release_id, year)
    _release_store(AppSettings()).fail(execution)
    typer.echo(execution.model_dump_json())


@source_app.command("inspect")
def inspect_source(
    source: Annotated[str, typer.Option("--source")],
    demo: Annotated[bool, typer.Option("--demo")] = False,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Inspect runtime source metadata; fixtures require explicit demo mode."""
    request = _request(source, 2024, 25 * 1024**3, dry_run=True)
    query = _query(0) if demo else build_production_query(source, AppSettings())
    inspection = query.inspect(request.source)
    typer.echo(inspection.model_dump_json())


@app.command("plan")
def plan(
    source: Annotated[str, typer.Option("--source")],
    year: Annotated[int, typer.Option("--year")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = True,
    maximum_bytes_billed: Annotated[int | None, typer.Option("--maximum-bytes-billed")] = None,
    demo_estimated_bytes: Annotated[
        int | None,
        typer.Option("--demo-estimated-bytes"),
    ] = None,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Return a bounded dry-run plan and stable JSON exit contract."""
    settings = AppSettings()
    request = _request(source, year, _maximum_bytes_billed(settings, maximum_bytes_billed), dry_run)
    try:
        if demo_estimated_bytes is not None:
            query = _query(demo_estimated_bytes)
        else:
            query = build_production_query(source, settings)
        result = estimate_batch(request, query)
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
    except ValidationError as error:
        typer.echo('{"status":"invalid_request"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error
    typer.echo(result.model_dump_json())


@app.command("run")
def run(
    source: Annotated[str, typer.Option("--source")],
    year: Annotated[int, typer.Option("--year")],
    *,
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
    demo: Annotated[bool, typer.Option("--demo")] = False,
    release_id: Annotated[str | None, typer.Option("--release-id")] = None,
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
) -> None:
    """Run production adapters; local fixtures require explicit demo mode."""
    settings = AppSettings()
    request = _request(source, year, settings.max_bytes_billed, dry_run)
    if not demo:
        provenance = _deployment_provenance()
        composition = build_production_composition(
            source,
            settings,
            git_sha=provenance.git_sha,
            image_digest=provenance.image_digest,
        )
        if dry_run:
            typer.echo(estimate_batch(request, composition.runtime.query).model_dump_json())
            return
        if release_id is None:
            typer.echo('{"status":"release_execution_required"}', err=True)
            raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION)
        execution = _release_execution(release_id, year)
        manifest = execute_batch(request, composition.runtime, composition.context)
        _release_store(settings).record(execution, manifest)
        typer.echo(manifest.model_dump_json())
        return
    query = _query(1024**3, snapshot_row_count=1)
    if dry_run:
        typer.echo(estimate_batch(request, query).model_dump_json())
        return
    manifests = InMemoryManifestStore()
    objects = InMemoryObjectStore()
    with TemporaryDirectory(prefix="alfabetizacao-batch-") as temp_directory:
        reference = Path(temp_directory) / "fixture.parquet"
        build_demo_file(SOURCE_CATALOG[source], reference, year=year)
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
