from pathlib import Path

import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.release_script_harness import (
    MANDATORY_RULES,
    insert_quality_results,
    promotion_options,
    release_database,
)

PROMOTE = Path("src/alfabetizacao_pipeline/releases/templates/promote_release.sql")
ROLLBACK = Path("src/alfabetizacao_pipeline/releases/templates/rollback_release.sql")
CLEANUP = Path("sql/quality/cleanup_releases.sql")


def test_promotion_rejects_duplicate_or_extra_quality_rows_before_dml() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        _ = connection.execute(
            """insert into release_results values
            ('release-b', 'required_keys', 0, 'pass', 'promote', 'duplicate', current_timestamp)"""
        )
        before = connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone()
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert (
            connection.execute("select release_id, prior_release_id from active_release").fetchone()
            == before
        )


def test_promotion_rejects_quality_evaluated_against_a_stale_active_release() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        _ = connection.execute(
            """
            update release_registry set status = 'inactive' where release_id = 'release-a';
            insert into release_registry values(
                'release-new', 'active', 2025, current_timestamp, current_timestamp,
                current_timestamp, 'release-a'
            );
            update active_release set release_id = 'release-new';
            """
        )

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-new", None)


def test_promotion_fails_closed_when_candidate_is_missing() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("missing-release"),
            )
        assert connection.execute("select release_id from active_release").fetchone() == (
            "release-a",
        )


@pytest.mark.parametrize("omitted_rule", [None, *MANDATORY_RULES])
def test_promotion_requires_nonempty_complete_quality_set(omitted_rule: str | None) -> None:
    with release_database() as connection:
        if omitted_rule is not None:
            insert_quality_results(connection, omitted_rule=omitted_rule)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert connection.execute("select release_id from active_release").fetchone() == (
            "release-a",
        )


def test_promotion_rejects_critical_and_promotes_complete_candidate() -> None:
    with release_database() as connection:
        insert_quality_results(connection, critical_rule="relationships")
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        _ = connection.execute("delete from release_results")
        insert_quality_results(connection)
        run_bigquery_script(
            connection,
            PROMOTE,
            options=promotion_options("release-b"),
        )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-b", "release-a")
        assert connection.execute(
            "select release_id, status from release_registry order by release_id"
        ).fetchall() == [("release-a", "inactive"), ("release-b", "active")]


def test_promotion_rejects_candidate_with_duplicate_registry_rows() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """insert into release_registry(
                release_id, status, created_at, promoted_at, completed_at
            ) values
            ('release-b', 'failed', date '2024-02-02', null, null)"""
        )
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", None)


def test_promotion_rejects_active_release_as_candidate_before_any_dml() -> None:
    with release_database() as connection:
        _ = connection.execute(
            "update release_registry set status = 'succeeded' where release_id = 'release-a'"
        )
        insert_quality_results(connection)
        _ = connection.execute("update release_results set release_id = 'release-a'")
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-a"),
            )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", None)
        assert connection.execute(
            "select status from release_registry where release_id = 'release-a'"
        ).fetchone() == ("succeeded",)


def test_promotion_rejects_active_pointer_with_self_referencing_prior() -> None:
    with release_database() as connection:
        _ = connection.execute("update active_release set prior_release_id = 'release-a'")
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", "release-a")


def test_promotion_rejects_active_pointer_with_inconsistent_registry_state() -> None:
    with release_database() as connection:
        _ = connection.execute(
            "update release_registry set status = 'succeeded' where release_id = 'release-a'"
        )
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=promotion_options("release-b"),
            )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", None)


def test_rollback_executes_delivered_script_and_restores_prior_release() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        run_bigquery_script(
            connection,
            PROMOTE,
            options=promotion_options("release-b"),
        )
        run_bigquery_script(
            connection,
            ROLLBACK,
            options=ScriptRunOptions(parameters={"reference_year": 2023}),
        )
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", None)


def test_cleanup_with_null_prior_preserves_active_and_deletes_only_eligible() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            insert into release_registry(
                release_id, status, created_at, promoted_at, completed_at
            ) values
                ('failed-old', 'failed', current_timestamp - interval 8 day, null, null),
                ('success-old', 'succeeded', current_timestamp - interval 31 day, null, null),
                ('failed-new', 'failed', current_timestamp - interval 6 day, null, null),
                ('success-new', 'succeeded', current_timestamp - interval 29 day, null, null);
            insert into release_files values
                ('release-a', 'active.csv'), ('failed-old', 'failed.csv'),
                ('success-old', 'success.csv'), ('failed-new', 'new.csv');
            """
        )
        run_bigquery_script(connection, CLEANUP)
        assert connection.execute(
            "select release_id from release_registry order by release_id"
        ).fetchall() == [
            ("failed-new",),
            ("release-a",),
            ("success-new",),
        ]
        assert connection.execute(
            "select release_id from release_files order by release_id"
        ).fetchall() == [("failed-new",), ("release-a",)]


def test_cleanup_preserves_nonnull_prior_even_when_old() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            update active_release set prior_release_id = 'release-b';
            update release_registry
            set created_at = current_timestamp - interval 31 day
            where release_id = 'release-b';
            insert into release_files values ('release-b', 'prior.csv');
            """
        )
        run_bigquery_script(connection, CLEANUP)
        assert connection.execute(
            "select release_id from release_registry order by release_id"
        ).fetchall() == [("release-a",), ("release-b",)]
        assert connection.execute("select release_id from release_files").fetchall() == [
            ("release-b",)
        ]
