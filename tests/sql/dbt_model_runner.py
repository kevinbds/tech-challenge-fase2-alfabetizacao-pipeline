import re
from collections.abc import Mapping
from pathlib import Path

import duckdb

from tests.sql.bigquery_script_runner import ScriptScalar, translate_bigquery_sql


def materialize_dbt_model(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    target_table: str,
    parameters: Mapping[str, ScriptScalar],
) -> None:
    sql = path.read_text(encoding="utf-8")
    sql = re.sub(r"\{\{\s*config\(.+?\)\s*\}\}", "", sql, count=1)
    sql = re.sub(
        r"\{\{\s*var\(\"release_id\"\)\s*\}\}",
        str(parameters["release_id"]),
        sql,
    )
    sql = re.sub(
        r"\{\{\s*var\(\"project_id\"\)\s*\}\}",
        "{{ project_id }}",
        sql,
    )
    sql = re.sub(r"\{\{\s*ref\('([a-z_]+)'\)\s*\}\}", r"\1", sql)
    translated = translate_bigquery_sql(sql, parameters)
    create_table = "create or replace table"
    statement = f"{create_table} {target_table} as {translated}"
    _ = connection.execute(statement)
