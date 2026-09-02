import re
from importlib.resources import files
from typing import Final

from alfabetizacao_pipeline.batch.errors import (
    InvalidReferenceYearError,
    InvalidTableIdentifierError,
)

MIN_REFERENCE_YEAR: Final = 2000
MAX_REFERENCE_YEAR: Final = 2100


def promotion_sql(table: str) -> str:
    """Render the canonical promotion transaction for an active-release table."""
    return _canonical_sql("promote_release.sql", _project_id(table))


def rollback_sql(table: str, reference_year: int) -> str:
    """Render the canonical historical rollback transaction for one reference year."""
    _validate_reference_year(reference_year)
    return _canonical_sql("rollback_release.sql", _project_id(table)).replace(
        "@reference_year", str(reference_year)
    )


def _validate_table(table: str) -> None:
    if (
        re.fullmatch(r"[a-z][a-z0-9-]{4,29}\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table)
        is None
    ):
        raise InvalidTableIdentifierError(table=table)


def _validate_reference_year(reference_year: int) -> None:
    if (
        type(reference_year) is not int
        or not MIN_REFERENCE_YEAR <= reference_year <= MAX_REFERENCE_YEAR
    ):
        raise InvalidReferenceYearError(value_type=type(reference_year).__name__)


def _project_id(table: str) -> str:
    _validate_table(table)
    project_id, dataset, table_name = table.split(".")
    if (dataset, table_name) != ("ops", "active_release"):
        raise InvalidTableIdentifierError(table=table)
    return project_id


def _canonical_sql(filename: str, project_id: str) -> str:
    source = files("alfabetizacao_pipeline.releases").joinpath("templates", filename)
    return source.read_text(encoding="utf-8").replace("{{ project_id }}", project_id)
