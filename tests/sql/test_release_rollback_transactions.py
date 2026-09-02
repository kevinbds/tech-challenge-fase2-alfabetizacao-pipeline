from pathlib import Path

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.release_script_harness import activate_release_b, release_database

ROLLBACK = Path("src/alfabetizacao_pipeline/releases/templates/rollback_release.sql")


def _snapshot(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[list[tuple[bool, str, str | None]], list[tuple[str, str]]]:
    pointer = connection.execute(
        "select singleton_key, release_id, prior_release_id from active_release"
    ).fetchall()
    registry = connection.execute(
        "select release_id, status from release_registry order by release_id, status"
    ).fetchall()
    return pointer, registry


@pytest.mark.parametrize(
    ("pointer_sql", "registry_sql"),
    [
        ("update active_release set prior_release_id = null", "select 1"),
        ("update active_release set prior_release_id = 'release-b'", "select 1"),
        (
            "update active_release set release_id = null, prior_release_id = 'release-a'",
            "select 1",
        ),
        (
            "update active_release set release_id = 'missing', prior_release_id = 'release-a'",
            "select 1",
        ),
        ("select 1", "delete from release_registry where release_id = 'release-b'"),
        (
            "select 1",
            (
                "insert into release_registry select * from release_registry "
                "where release_id = 'release-b'"
            ),
        ),
        (
            "select 1",
            "update release_registry set status = 'failed' where release_id = 'release-b'",
        ),
        ("select 1", "delete from release_registry where release_id = 'release-a'"),
        (
            "select 1",
            "update release_registry set status = 'failed' where release_id = 'release-a'",
        ),
        (
            "select 1",
            (
                "insert into release_registry select * from release_registry "
                "where release_id = 'release-a'"
            ),
        ),
    ],
    ids=[
        "prior-null",
        "self-reference",
        "current-null",
        "current-registry-missing",
        "current-row-missing",
        "current-row-duplicate",
        "current-status-inconsistent",
        "prior-registry-missing",
        "prior-status-inconsistent",
        "prior-row-duplicate",
    ],
)
def test_rollback_rejects_invalid_pointer_or_registry_without_mutation(
    pointer_sql: str,
    registry_sql: str,
) -> None:
    with release_database() as connection:
        activate_release_b(connection)
        _ = connection.execute(pointer_sql)
        _ = connection.execute(registry_sql)
        before = _snapshot(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                ROLLBACK,
                options=ScriptRunOptions(parameters={"reference_year": 2023}),
            )
        assert _snapshot(connection) == before


def test_rollback_stale_pointer_cas_rolls_back_every_mutation() -> None:
    with release_database() as connection:
        activate_release_b(connection)
        before = _snapshot(connection)

        def change_pointer(
            statement_index: int,
            statement: str,
            connection: duckdb.DuckDBPyConnection,
        ) -> None:
            del statement_index
            if statement.lower().startswith("update ") and "active_release" in statement:
                _ = connection.execute("update active_release set release_id = 'release-stale'")

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                ROLLBACK,
                options=ScriptRunOptions(
                    parameters={"reference_year": 2023},
                    before_statement=change_pointer,
                ),
            )
        assert _snapshot(connection) == before


def test_rollback_intermediate_registry_failure_is_atomic() -> None:
    with release_database() as connection:
        activate_release_b(connection)
        before = _snapshot(connection)

        def invalidate_current(
            statement_index: int,
            statement: str,
            connection: duckdb.DuckDBPyConnection,
        ) -> None:
            del statement_index
            if statement.lower().startswith("update ") and "current_release" in statement:
                _ = connection.execute(
                    "update release_registry set status = 'failed' where release_id = 'release-b'"
                )

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                ROLLBACK,
                options=ScriptRunOptions(
                    parameters={"reference_year": 2023},
                    before_statement=invalidate_current,
                ),
            )
        assert _snapshot(connection) == before
