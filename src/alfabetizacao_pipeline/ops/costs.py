from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Annotated, override

import typer
from pydantic import ValidationError

from alfabetizacao_pipeline.errors import ExitCode
from alfabetizacao_pipeline.ops.models import (
    CostCatalog,
    CostReport,
    Currency,
    InvalidCostResponse,
)
from alfabetizacao_pipeline.types import OutputFormat

DEFAULT_CATALOG = Path("ops/cost_profiles.yml")
TIB = Decimal(1024**4)
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ProfileNotFoundError(Exception):
    """Raised when a requested cost profile is absent."""

    profile: str

    @override
    def __str__(self) -> str:
        return f"cost profile not found: {self.profile}"


app = typer.Typer(
    name="costs",
    help="Estima o custo local com premissas versionadas, sem acessar a nuvem.",
    no_args_is_help=True,
    rich_markup_mode=None,
)


@app.callback()
def main() -> None:
    """Expose cost operations as an explicit command group."""


def load_catalog(path: Path) -> CostCatalog:
    """Parse a versioned JSON-compatible YAML cost catalog."""
    return CostCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def estimate_profile(catalog: CostCatalog, profile_name: str) -> CostReport:
    """Calculate the exact estimate for one named profile."""
    try:
        request = catalog.profiles[profile_name]
    except KeyError as error:
        raise ProfileNotFoundError(profile=profile_name) from error

    bigquery = _money(Decimal(request.bytes_processed) / TIB * catalog.rates.bigquery_per_tib)
    dataflow = _money(
        Decimal(request.workers) * request.worker_hours * catalog.rates.dataflow_per_worker_hour
    )
    storage = _money(request.storage_gb_month * catalog.rates.storage_per_gb_month)
    pubsub = _money(request.pubsub_gib * catalog.rates.pubsub_per_gib)
    return CostReport(
        profile=profile_name,
        currency=request.currency,
        bigquery=bigquery,
        dataflow=dataflow,
        storage=storage,
        pubsub=pubsub,
        total=bigquery + dataflow + storage + pubsub,
    )


@app.command("estimate")
def estimate(
    profile: Annotated[str, typer.Option("--profile", min=1)] = "demo",
    _output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.JSON,
    currency: Annotated[Currency | None, typer.Option("--currency")] = None,
    catalog_path: Annotated[Path, typer.Option("--catalog", exists=True)] = DEFAULT_CATALOG,
) -> None:
    """Print a deterministic JSON estimate for a named profile."""
    try:
        catalog = load_catalog(catalog_path)
        report = estimate_profile(catalog, profile)
    except ValidationError as error:
        response = InvalidCostResponse(
            error_code="invalid_cost_catalog",
            error_count=error.error_count(),
        )
        typer.echo(response.model_dump_json(), err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error
    except ProfileNotFoundError as error:
        response = InvalidCostResponse(error_code="profile_not_found", error_count=1)
        typer.echo(response.model_dump_json(), err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION) from error

    if currency is not None and currency is not report.currency:
        typer.echo('{"status":"invalid","error":"currency mismatch"}', err=True)
        raise typer.Exit(code=ExitCode.INVALID_CONFIGURATION)
    typer.echo(report.model_dump_json())


if __name__ == "__main__":
    app()
