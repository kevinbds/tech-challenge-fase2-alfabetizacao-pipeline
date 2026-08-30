import re

# ruff: noqa: S608  # Runner executes only repository-owned SQL fixtures.
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import override

import duckdb


@dataclass(frozen=True, slots=True)
class ScriptAssertionError(Exception):
    message: str

    @override
    def __str__(self) -> str:
        return self.message


def _sql_literal(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def _translate(statement: str, variables: Mapping[str, str]) -> str:
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
    for name, literal in sorted(variables.items(), key=lambda item: -len(item[0])):
        translated = re.sub(rf"\b{re.escape(name)}\b", literal, translated)
    return translated


def run_bigquery_script(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    *,
    release_id: str | None = None,
) -> None:
    variables: dict[str, str] = {}
    statements = [
        part.strip() for part in path.read_text(encoding="utf-8").split(";") if part.strip()
    ]
    for statement in statements:
        lowered = statement.lower()
        if lowered.startswith("declare "):
            match = re.fullmatch(
                r"declare\s+([a-z_]+)\s+[^\s]+(?:\s+default\s+(.+))?",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert match is not None
            name, default = match.groups()
            variables[name] = "null" if default is None else _sql_literal(release_id)
            continue
        if lowered.startswith("set ("):
            match = re.fullmatch(
                r"set\s+\(([^)]+)\)\s*=\s*\((.+)\)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert match is not None
            names = [name.strip() for name in match.group(1).split(",")]
            query = _translate(match.group(2), variables).strip()
            query_parts = re.fullmatch(
                r"select\s+(.+?)\s+from\s+(.+)", query, flags=re.IGNORECASE | re.DOTALL
            )
            assert query_parts is not None
            expressions = [expression.strip() for expression in query_parts.group(1).split(",")]
            assert len(expressions) == len(names)
            variables.update(
                {
                    name: f"(select {expression} from {query_parts.group(2)})"
                    for name, expression in zip(names, expressions, strict=True)
                }
            )
            continue
        if lowered.startswith("set "):
            match = re.fullmatch(
                r"set\s+([a-z_]+)\s*=\s*\((.+)\)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert match is not None
            variables[match.group(1)] = f"({_translate(match.group(2), variables)})"
            continue
        if lowered.startswith("assert "):
            match = re.fullmatch(
                r"assert\s+(.+?)\s+as\s+'([^']+)'",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            assert match is not None
            passed = connection.execute(
                "select " + _translate(match.group(1), variables)
            ).fetchone()
            if passed != (True,):
                raise ScriptAssertionError(message=match.group(2))
            continue
        _ = connection.execute(_translate(statement, variables))
