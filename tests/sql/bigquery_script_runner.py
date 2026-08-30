import re

# ruff: noqa: S608  # Runner executes only repository-owned SQL fixtures.
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, override

import duckdb


@dataclass(frozen=True, slots=True)
class ScriptAssertionError(Exception):
    message: str

    @override
    def __str__(self) -> str:
        return self.message


type ScriptScalar = str | int | float | bool | None


class StatementHook(Protocol):
    def __call__(
        self,
        statement_index: int,
        statement: str,
        connection: duckdb.DuckDBPyConnection,
    ) -> None: ...


def _empty_parameters() -> dict[str, ScriptScalar]:
    return {}


@dataclass(frozen=True, slots=True)
class ScriptRunOptions:
    parameters: Mapping[str, ScriptScalar] = field(default_factory=_empty_parameters)
    before_statement: StatementHook | None = None


@dataclass(frozen=True, slots=True)
class _ScriptContext:
    connection: duckdb.DuckDBPyConnection
    path: Path
    parameters: Mapping[str, ScriptScalar]
    variables: dict[str, str]


def _sql_literal(value: ScriptScalar) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return repr(value)


def _translate(
    statement: str,
    variables: Mapping[str, str],
    parameters: Mapping[str, ScriptScalar],
    row_count: int,
) -> str:
    translated = re.sub(
        r"`\{\{ project_id \}\}\.(?:ops|quality)\.([a-z_]+)`",
        r"\1",
        statement,
    )
    translated = re.sub(
        r"timestamp_sub\(current_timestamp\(\), interval (\d+) day\)",
        r"current_timestamp - interval \1 day",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"current_timestamp\(\)", "current_timestamp", translated, flags=re.IGNORECASE
    )
    translated = re.sub(r"select\s+as\s+struct", "select", translated, flags=re.IGNORECASE)
    translated = translated.replace("@@row_count", str(row_count))
    translated = re.sub(
        r"@([a-z_]+)",
        lambda match: _sql_literal(parameters[match.group(1)]),
        translated,
    )
    for name, literal in sorted(variables.items(), key=lambda item: -len(item[0])):
        translated = re.sub(rf"\b{re.escape(name)}\b", literal, translated)
    return translated


def _assert_script(passed: tuple[bool] | None, message: str) -> None:
    if passed != (True,):
        raise ScriptAssertionError(message=message)


def _handle_assignment(
    context: _ScriptContext,
    statement: str,
    statement_index: int,
    row_count: int,
) -> bool:
    lowered = statement.lower()
    if lowered.startswith("declare "):
        match = re.fullmatch(
            r"declare\s+([a-z_]+)\s+[^\s]+(?:\s+default\s+(.+))?",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        name, default = match.groups()
        if default is None:
            context.variables[name] = "null"
        else:
            parameter = re.fullmatch(r"@([a-z_]+)", default.strip())
            assert parameter is not None
            context.variables[name] = _sql_literal(context.parameters[parameter.group(1)])
        return True
    if lowered.startswith("set ("):
        match = re.fullmatch(
            r"set\s+\(([^)]+)\)\s*=\s*\((.+)\)",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        names = [name.strip() for name in match.group(1).split(",")]
        query = _translate(match.group(2), context.variables, context.parameters, row_count).strip()
        query_parts = re.fullmatch(
            r"select\s+(.+?)\s+from\s+(.+)",
            query,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert query_parts is not None
        expressions = [expression.strip() for expression in query_parts.group(1).split(",")]
        assert len(expressions) == len(names)
        assert all(re.fullmatch(r"[a-z_]+", expression) for expression in expressions)
        set_table = f"_script_{context.path.stem}_{statement_index}"
        _ = context.connection.execute(f"create or replace temp table {set_table} as {query}")
        context.variables.update(
            {
                name: f"(select {expression} from {set_table})"
                for name, expression in zip(names, expressions, strict=True)
            }
        )
        return True
    if lowered.startswith("set "):
        match = re.fullmatch(
            r"set\s+([a-z_]+)\s*=\s*\((.+)\)",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert match is not None
        set_table = f"_script_{context.path.stem}_{statement_index}"
        query = _translate(match.group(2), context.variables, context.parameters, row_count)
        _ = context.connection.execute(
            f"create or replace temp table {set_table} as select ({query}) as value"
        )
        context.variables[match.group(1)] = f"(select value from {set_table})"
        return True
    return False


def _handle_assertion(context: _ScriptContext, statement: str, row_count: int) -> bool:
    if not statement.lower().startswith("assert "):
        return False
    match = re.fullmatch(
        r"assert\s+(.+?)\s+as\s+'([^']+)'",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None
    passed = context.connection.execute(
        "select " + _translate(match.group(1), context.variables, context.parameters, row_count)
    ).fetchone()
    _assert_script(passed, match.group(2))
    return True


def run_bigquery_script(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    *,
    options: ScriptRunOptions | None = None,
) -> None:
    active_options = options or ScriptRunOptions()
    context = _ScriptContext(
        connection=connection,
        path=path,
        parameters=active_options.parameters,
        variables={},
    )
    row_count = 0
    in_transaction = False
    statements = [
        part.strip() for part in path.read_text(encoding="utf-8").split(";") if part.strip()
    ]
    try:
        for statement_index, statement in enumerate(statements):
            if active_options.before_statement is not None:
                active_options.before_statement(statement_index, statement, connection)
            lowered = statement.lower()
            if lowered == "begin transaction":
                _ = connection.execute(statement)
                in_transaction = True
                continue
            if lowered == "commit transaction":
                _ = connection.execute(statement)
                in_transaction = False
                continue
            if _handle_assignment(context, statement, statement_index, row_count):
                continue
            if _handle_assertion(context, statement, row_count):
                continue
            translated = _translate(statement, context.variables, context.parameters, row_count)
            if lowered.startswith(("delete ", "insert ", "update ")):
                row_count = len(connection.execute(translated + " returning 1").fetchall())
            else:
                _ = connection.execute(translated)
    except (ScriptAssertionError, duckdb.Error):
        if in_transaction:
            _ = connection.execute("rollback transaction")
        raise
