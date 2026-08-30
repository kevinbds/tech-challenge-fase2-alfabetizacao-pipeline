from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter, ValidationError

from alfabetizacao_pipeline.batch.models import BatchManifest
from alfabetizacao_pipeline.releases.selector import select_latest_completed
from alfabetizacao_pipeline.releases.sql import promotion_sql, rollback_sql

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


@app.command("select")
def select(
    manifests: Annotated[Path, typer.Option("--manifests")],
    release_id: Annotated[str, typer.Option("--release-id")],
) -> None:
    """Select latest completed manifests from a typed local JSON fixture."""
    try:
        parsed = TypeAdapter(tuple[BatchManifest, ...]).validate_json(manifests.read_bytes())
    except (OSError, ValidationError) as error:
        typer.echo('{"status":"invalid_manifests"}', err=True)
        raise typer.Exit(code=2) from error
    release = select_latest_completed(parsed, release_id, datetime.now(tz=UTC))
    typer.echo(release.model_dump_json())


@app.command("promote")
def promote(
    release_id: Annotated[str, typer.Option("--release-id")],
    table: Annotated[str, typer.Option("--table")],
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
) -> None:
    """Render parameterized promotion SQL without executing cloud DML."""
    if not dry_run:
        typer.echo('{"status":"cloud_authorization_required"}', err=True)
        raise typer.Exit(code=5)
    del release_id
    typer.echo(promotion_sql(table))


@app.command("rollback")
def rollback(
    active_release_id: Annotated[str, typer.Option("--active-release-id")],
    previous_release_id: Annotated[str | None, typer.Option("--previous-release-id")] = None,
    table: Annotated[str, typer.Option("--table")] = "project.ops.active_release",
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
) -> None:
    """Render transactional pointer rollback SQL without cloud execution."""
    if not dry_run:
        typer.echo('{"status":"cloud_authorization_required"}', err=True)
        raise typer.Exit(code=5)
    del active_release_id, previous_release_id
    typer.echo(rollback_sql(table))


if __name__ == "__main__":
    app()
