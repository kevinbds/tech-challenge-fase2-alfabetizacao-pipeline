from collections.abc import Mapping
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined

from tests.sql.bigquery_script_runner import ScriptScalar, translate_bigquery_sql

type ConfigValue = str | bool | list[str]


def _config(**_settings: ConfigValue) -> str:
    return ""


def _ref(model_name: str) -> str:
    return model_name


def _source(_source_name: str, table_name: str) -> str:
    return table_name


def _days_since(expression: str) -> str:
    return f"date_diff('day', cast({expression} as date), current_date)"


def materialize_dbt_model(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    target_table: str,
    parameters: Mapping[str, ScriptScalar],
) -> None:
    environment = Environment(undefined=StrictUndefined)  # noqa: S701

    def resolve_var(name: str) -> ScriptScalar:
        return parameters.get(name, f"{{{{ {name} }}}}")

    template = environment.from_string(
        path.read_text(encoding="utf-8"),
        globals={
            "config": _config,
            "ref": _ref,
            "source": _source,
            "var": resolve_var,
            "days_since": _days_since,
        },
    )
    sql = template.render()
    translated = translate_bigquery_sql(sql, parameters)
    statement = f"create or replace table {target_table} as {translated}"
    _ = connection.execute(statement)
