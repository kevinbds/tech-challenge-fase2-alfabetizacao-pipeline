from typing import Annotated

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline import __version__
from alfabetizacao_pipeline.config import AppSettings, ConfigCheck
from alfabetizacao_pipeline.errors import ExitCode
from alfabetizacao_pipeline.types import OutputFormat

app = typer.Typer(
    name="alfabetizacao",
    help="Opera o pipeline híbrido de indicadores de alfabetização.",
    no_args_is_help=True,
    rich_markup_mode=None,
)
config_app = typer.Typer(
    help="Valida a configuração local sem acessar a nuvem.",
    rich_markup_mode=None,
)
app.add_typer(config_app, name="config")


@app.command("version")
def version() -> None:
    """Print the installed application version."""
    typer.echo(__version__)


@config_app.command("check")
def config_check(
    _output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Formato da resposta."),
    ] = OutputFormat.JSON,
) -> None:
    """Validate local settings without making a cloud request."""
    try:
        settings = AppSettings()
    except ValidationError as error:
        typer.echo(
            f'{{"status":"invalid","error_count":{error.error_count()}}}',
            err=True,
        )
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error

    result = ConfigCheck(config=settings)
    typer.echo(result.model_dump_json())
