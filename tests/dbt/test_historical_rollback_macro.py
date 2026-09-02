import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import duckdb
import pytest


def _run_operation(
    database: Path, arguments: dict[str, int | str]
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DBT_DUCKDB_PATH"] = str(database)
    return subprocess.run(
        [
            "dbt",
            "run-operation",
            "rollback_release",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--target",
            "offline",
            "--args",
            json.dumps(arguments),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _create_history(database: Path) -> None:
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            create schema ops;
            create table ops.active_release(
                singleton_key boolean, release_id varchar,
                prior_release_id varchar, promoted_at timestamp
            );
            insert into ops.active_release values
                (true, 'release-d', 'release-c', timestamp '2026-01-01');
            create table ops.release_registry(
                release_id varchar, status varchar, reference_year integer,
                created_at timestamp, completed_at timestamp, promoted_at timestamp,
                baseline_release_id varchar
            );
            insert into ops.release_registry values
                ('release-a', 'inactive', 2023, current_timestamp,
                 current_timestamp, current_timestamp, '__bootstrap__'),
                ('release-b', 'inactive', 2024, current_timestamp,
                 current_timestamp, current_timestamp, 'release-a'),
                ('release-c', 'inactive', 2024, current_timestamp,
                 current_timestamp, current_timestamp, 'release-b'),
                ('release-d', 'active', 2026, current_timestamp,
                 current_timestamp, current_timestamp, 'release-c');
            """
        )


def _create_deep_history(database: Path) -> None:
    _create_history(database)
    releases = [
        (
            f"release-{index:03d}",
            "active" if index == 401 else "inactive",
            "__bootstrap__" if index == 0 else f"release-{index - 1:03d}",
        )
        for index in range(402)
    ]
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute("delete from ops.release_registry")
        _ = connection.executemany(
            """
            insert into ops.release_registry values
                (?, ?, 2024, current_timestamp, current_timestamp,
                 current_timestamp, ?)
            """,
            releases,
        )
        _ = connection.execute(
            """
            update ops.active_release
            set release_id = 'release-401', prior_release_id = 'release-400'
            """
        )


def _snapshot(
    database: Path,
) -> tuple[
    list[tuple[bool, str, str | None, datetime]],
    list[tuple[str, str, int, datetime, datetime, datetime, str | None]],
]:
    with duckdb.connect(str(database), read_only=True) as connection:
        pointer = connection.execute("select * from ops.active_release").fetchall()
        registry = connection.execute(
            "select * from ops.release_registry order by release_id, status"
        ).fetchall()
    return pointer, registry


def test_macro_rolls_back_directly_and_retry_does_not_toggle(tmp_path: Path) -> None:
    database = tmp_path / "history.duckdb"
    _create_history(database)

    first = _run_operation(database, {"reference_year": 2024})
    assert first.returncode == 0, first.stdout + first.stderr
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "select release_id, prior_release_id from ops.active_release"
        ).fetchone() == ("release-c", "release-b")
    after_first = _snapshot(database)

    retry = _run_operation(database, {"reference_year": 2024})
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert _snapshot(database) == after_first

    older = _run_operation(database, {"reference_year": 2023})
    assert older.returncode == 0, older.stdout + older.stderr
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "select release_id, prior_release_id from ops.active_release"
        ).fetchone() == ("release-a", None)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"reference_year": "2024; drop table ops.active_release"}],
)
def test_macro_rejects_invalid_year_before_querying(
    tmp_path: Path, arguments: dict[str, int | str]
) -> None:
    database = tmp_path / "invalid.duckdb"
    _create_history(database)
    before = _snapshot(database)

    result = _run_operation(database, arguments)

    assert result.returncode != 0
    assert "invalid reference_year" in result.stdout + result.stderr
    assert _snapshot(database) == before


@pytest.mark.parametrize("year", [2025, 2027])
def test_macro_rejects_absent_or_future_year_without_mutation(tmp_path: Path, year: int) -> None:
    database = tmp_path / f"year-{year}.duckdb"
    _create_history(database)
    before = _snapshot(database)

    result = _run_operation(database, {"reference_year": year})

    assert result.returncode != 0
    assert _snapshot(database) == before


def test_macro_rejects_a_cycle_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "cycle.duckdb"
    _create_history(database)
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            update ops.release_registry set baseline_release_id = 'release-d'
            where release_id = 'release-b'
            """
        )
    before = _snapshot(database)

    result = _run_operation(database, {"reference_year": 2023})

    assert result.returncode != 0
    assert "release ancestry" in result.stdout + result.stderr
    assert _snapshot(database) == before


def test_macro_rejects_history_beyond_depth_limit_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "deep.duckdb"
    _create_deep_history(database)
    before = _snapshot(database)

    result = _run_operation(database, {"reference_year": 2023})

    assert result.returncode != 0
    assert "release ancestry exceeds maximum depth" in result.stdout + result.stderr
    assert _snapshot(database) == before
