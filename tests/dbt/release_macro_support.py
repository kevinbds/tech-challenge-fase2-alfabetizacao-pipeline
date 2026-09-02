import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


@dataclass(frozen=True, slots=True)
class QueryColumn:
    cells: tuple[object, ...]

    def values(self) -> tuple[object, ...]:
        return self.cells


@dataclass(frozen=True, slots=True)
class QueryResult:
    values: tuple[object, ...] = ()
    row_count: int = 1

    @property
    def columns(self) -> tuple[QueryColumn, ...]:
        return tuple(QueryColumn((value,)) for value in self.values)

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        return tuple(self.values for _ in range(self.row_count))


class CompilerErrors:
    @staticmethod
    def raise_compiler_error(message: str) -> NoReturn:
        raise RuntimeError(message)


def identity(value: object) -> object:
    return value


def macro_source(*macro_files: str) -> str:
    macro_directory = Path("dbt/macros")
    return "\n".join(
        (macro_directory / macro_file).read_text(encoding="utf-8")
        for macro_file in ("release_control.sql", *macro_files)
    )


def run_operation(database: Path, macro: str, arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DBT_DUCKDB_PATH"] = str(database)
    return subprocess.run(
        [
            "dbt",
            "run-operation",
            macro,
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--target",
            "offline",
            "--args",
            arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
