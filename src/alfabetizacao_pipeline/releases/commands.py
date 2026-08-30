from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from alfabetizacao_pipeline.batch.errors import IncompleteRunError
from alfabetizacao_pipeline.batch.models import BatchManifest
from alfabetizacao_pipeline.releases.selector import select_latest_completed
from alfabetizacao_pipeline.releases.sql import promotion_sql, rollback_sql

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


def _required_identifier(value: str | None) -> str:
    if value is None or not value.strip():
        typer.echo('{"status":"invalid_release_id"}', err=True)
        raise typer.Exit(code=2)
    return value


@app.command("select")
def select(
    manifests: Annotated[Path, typer.Option("--manifests")],
    release_id: Annotated[str, typer.Option("--release-id")],
    year: Annotated[int, typer.Option("--year")],
    expected_sources: Annotated[list[str], typer.Option("--expected-source")],
) -> None:
    """Select latest completed manifests from a typed local JSON fixture."""
    try:
        parsed = TypeAdapter(tuple[BatchManifest, ...]).validate_json(manifests.read_bytes())
    except (OSError, ValidationError) as error:
        typer.echo('{"status":"invalid_manifests"}', err=True)
        raise typer.Exit(code=2) from error
    expected_keys = frozenset((source, year) for source in expected_sources)
    try:
        release = select_latest_completed(
            parsed,
            release_id,
            datetime.now(tz=UTC),
            expected_keys=expected_keys,
        )
    except IncompleteRunError as error:
        typer.echo('{"status":"incomplete_release"}', err=True)
        raise typer.Exit(code=2) from error
    typer.echo(release.model_dump_json())


@app.command("promote")
def promote(
    release_id: Annotated[str, typer.Option("--release-id")],
    table: Annotated[str, typer.Option("--table")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
) -> None:
    """Render parameterized promotion SQL without executing cloud DML."""
    _ = _required_identifier(release_id)
    if not dry_run:
        typer.echo('{"status":"cloud_authorization_required"}', err=True)
        raise typer.Exit(code=5)
    typer.echo(promotion_sql(table))


@app.command("rollback")
def rollback(
    active_release_id: Annotated[str, typer.Option("--active-release-id")],
    previous_release_id: Annotated[str | None, typer.Option("--previous-release-id")] = None,
    table: Annotated[str, typer.Option("--table")] = "project.ops.active_release",
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
) -> None:
    """Render transactional pointer rollback SQL without cloud execution."""
    _ = _required_identifier(active_release_id)
    _ = _required_identifier(previous_release_id)
    if not dry_run:
        typer.echo('{"status":"cloud_authorization_required"}', err=True)
        raise typer.Exit(code=5)
    typer.echo(rollback_sql(table))


if __name__ == "__main__":
    app()
