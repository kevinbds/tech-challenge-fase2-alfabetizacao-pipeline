from pathlib import Path
from typing import Annotated

import typer

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.schema_reference.builder import build_reference_file

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


@app.callback()
def main() -> None:
    """Expose schema-reference commands as an explicit Typer group."""


@app.command("build-reference")
def build_reference(
    source: Annotated[str, typer.Option("--source")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Build a local zero-row Parquet schema artifact for one source."""
    try:
        contract = SOURCE_CATALOG[source]
    except KeyError as error:
        typer.echo('{"status":"invalid_source"}', err=True)
        raise typer.Exit(code=2) from error
    typer.echo(build_reference_file(contract, output).model_dump_json())


if __name__ == "__main__":
    app()
