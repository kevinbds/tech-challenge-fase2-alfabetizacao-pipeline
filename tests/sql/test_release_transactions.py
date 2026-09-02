from pathlib import Path

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.evaluate_release_harness import persist_quality_results
from tests.sql.release_script_harness import (
    insert_quality_results,
    promotion_options,
    release_database,
)

PROMOTE = Path("src/alfabetizacao_pipeline/releases/templates/promote_release.sql")
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


def test_runner_executes_statement_hook(tmp_path: Path) -> None:
    script = tmp_path / "hook.sql"
    _ = script.write_text(
        "begin transaction; update state set value = 2; commit transaction;",
        encoding="utf-8",
    )
    calls: list[str] = []

    def before_statement(
        statement_index: int,
        statement: str,
        connection: duckdb.DuckDBPyConnection,
    ) -> None:
        del statement_index
        calls.append(statement)
        if statement.lower().startswith("update state"):
            _ = connection.execute("update state set value = 3")

    with duckdb.connect(":memory:") as connection:
        _ = connection.execute("create table state(value int); insert into state values (1)")
        run_bigquery_script(
            connection,
            script,
            options=ScriptRunOptions(before_statement=before_statement),
        )
        assert connection.execute("select value from state").fetchone() == (2,)
    assert len(calls) == 3


def test_promotion_stale_pointer_cas_rolls_back_every_mutation() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
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
                PROMOTE,
                options=promotion_options("release-b", before_statement=change_pointer),
            )
        assert _snapshot(connection) == before


def test_promotion_intermediate_registry_failure_rolls_back_pointer() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        before = _snapshot(connection)

        def invalidate_candidate(
            statement_index: int,
            statement: str,
            connection: duckdb.DuckDBPyConnection,
        ) -> None:
            del statement_index
            if statement.lower().startswith("update ") and "candidate_release" in statement:
                _ = connection.execute(
                    "update release_registry set status = 'failed' where release_id = 'release-b'"
                )

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b", before_statement=invalidate_candidate),
            )
        assert _snapshot(connection) == before


def test_evaluate_persist_then_promote_uses_produced_catalog() -> None:
    with release_database() as connection:
        persist_quality_results(connection)
        run_bigquery_script(
            connection,
            PROMOTE,
            options=promotion_options("release-b"),
        )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-b", "release-a")
        assert connection.execute(
            "select count(*), count(distinct rule_id) from release_results"
        ).fetchone() == (13, 13)
        assert connection.execute(
            "select release_id, status from release_registry order by release_id"
        ).fetchall() == [("release-a", "inactive"), ("release-b", "active")]


def test_first_promotion_from_bootstrap_keeps_null_predecessor_and_rollback_is_idempotent() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            delete from release_registry where release_id = 'release-a';
            insert into release_registry values
                ('__bootstrap__', 'active', null, timestamp '2024-01-01',
                 timestamp '2024-01-01', current_timestamp, null);
            update active_release
            set release_id = '__bootstrap__', prior_release_id = null;
            update release_registry
            set baseline_release_id = '__bootstrap__'
            where release_id = 'release-b';
            """
        )
        insert_quality_results(connection)

        run_bigquery_script(
            connection,
            PROMOTE,
            options=promotion_options("release-b"),
        )

        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-b", None)
        assert connection.execute(
            "select release_id, status from release_registry order by release_id"
        ).fetchall() == [("__bootstrap__", "inactive"), ("release-b", "active")]

        run_bigquery_script(
            connection,
            ROLLBACK,
            options=ScriptRunOptions(parameters={"reference_year": 2024}),
        )

        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-b", None)


def test_evaluate_persisted_critical_rule_blocks_promotion() -> None:
    with release_database() as connection:
        persist_quality_results(connection)
        _ = connection.execute(
            """insert into quarantine_conflicting_duplicates values
            ('release-b', 'student-key', 'payload-a')"""
        )
        persist_quality_results(connection)
        before = _snapshot(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert _snapshot(connection) == before
