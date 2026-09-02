from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.release_script_harness import release_database

ROLLBACK = Path("src/alfabetizacao_pipeline/releases/templates/rollback_release.sql")
type SqlScalar = bool | str | int | datetime | None


def _historical_database() -> duckdb.DuckDBPyConnection:
    connection = release_database()
    _ = connection.execute(
        """
        update active_release
        set release_id = 'release-d', prior_release_id = 'release-c';
        update release_registry set status = 'inactive' where release_id = 'release-a';
        update release_registry set status = 'inactive' where release_id = 'release-b';
        insert into release_registry values
            ('release-c', 'inactive', 2024, timestamp '2024-03-01', null,
             current_timestamp, 'release-b'),
            ('release-d', 'active', 2026, timestamp '2026-01-01',
             timestamp '2026-01-01', current_timestamp, 'release-c');
        """
    )
    return connection


def _snapshot(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[list[tuple[SqlScalar, ...]], list[tuple[SqlScalar, ...]]]:
    pointer = connection.execute("select * from active_release").fetchall()
    registry = connection.execute(
        "select * from release_registry order by release_id, status"
    ).fetchall()
    return pointer, registry


def _rollback(connection: duckdb.DuckDBPyConnection, year: int) -> None:
    run_bigquery_script(
        connection,
        ROLLBACK,
        options=ScriptRunOptions(parameters={"reference_year": year}),
    )


def test_rollback_targets_nearest_year_and_retry_is_idempotent() -> None:
    with _historical_database() as connection:
        _rollback(connection, 2024)
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-c", "release-b")
        first = _snapshot(connection)

        _rollback(connection, 2024)
        assert _snapshot(connection) == first

        _rollback(connection, 2023)
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", None)
        assert connection.execute(
            "select status from release_registry where release_id = 'release-d'"
        ).fetchone() == ("inactive",)


@pytest.mark.parametrize("year", [2025, 2027])
def test_rollback_rejects_absent_or_future_year_without_mutation(year: int) -> None:
    with _historical_database() as connection:
        before = _snapshot(connection)
        with pytest.raises(ScriptAssertionError):
            _rollback(connection, year)
        assert _snapshot(connection) == before


def test_rollback_rejects_a_cycle_without_mutation() -> None:
    with _historical_database() as connection:
        _ = connection.execute(
            """
            update release_registry set baseline_release_id = 'release-d'
            where release_id = 'release-b'
            """
        )
        before = _snapshot(connection)
        with pytest.raises(ScriptAssertionError):
            _rollback(connection, 2023)
        assert _snapshot(connection) == before
