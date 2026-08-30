from pathlib import Path

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)

PROMOTE = Path("sql/quality/promote_release.sql")
ROLLBACK = Path("sql/quality/rollback_release.sql")
CLEANUP = Path("sql/quality/cleanup_releases.sql")
MANDATORY_RULES = (
    "required_keys",
    "uniqueness_after_quarantine",
    "relationships",
    "gold_core_nulls",
    "optional_null_delta",
    "percentage_ranges",
    "non_negative_measurements",
    "proportions_sum",
    "repeated_evaluation_or_target_rate",
    "partition_volume",
    "pipeline_freshness",
    "identical_duplicate",
    "conflicting_duplicate",
)


def release_database() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    _ = connection.execute(
        """
        create table active_release(
            singleton_key boolean,
            release_id varchar,
            prior_release_id varchar,
            promoted_at timestamp
        );
        insert into active_release values (true, 'release-a', null, timestamp '2024-01-01');
        create table release_registry(
            release_id varchar, status varchar, created_at timestamp, promoted_at timestamp,
            completed_at timestamp
        );
        insert into release_registry values
            ('release-a', 'active', timestamp '2024-01-01',
             timestamp '2024-01-01', current_timestamp),
            ('release-b', 'succeeded', timestamp '2024-02-01', null, current_timestamp);
        create table release_results(
            release_id varchar,
            rule_id varchar,
            metric_value double,
            severity varchar,
            action varchar,
            details varchar
        );
        create table release_files(release_id varchar, file_name varchar);
        """
    )
    return connection


def insert_quality_results(
    connection: duckdb.DuckDBPyConnection,
    *,
    omitted_rule: str | None = None,
    critical_rule: str | None = None,
) -> None:
    rows = [
        (
            "release-b",
            rule,
            0.0,
            "critical" if rule == critical_rule else "pass",
            "quarantine_and_block" if rule == critical_rule else "promote",
        )
        for rule in MANDATORY_RULES
        if rule != omitted_rule
    ]
    rows_with_details = [(*row, "test_fixture") for row in rows]
    _ = connection.executemany(
        "insert into release_results values (?, ?, ?, ?, ?, ?)", rows_with_details
    )


def test_promotion_rejects_duplicate_or_extra_quality_rows_before_dml() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        _ = connection.execute(
            """insert into release_results values
            ('release-b', 'required_keys', 0, 'pass', 'promote', 'duplicate')"""
        )
        before = connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone()
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
            )
        assert (
            connection.execute("select release_id, prior_release_id from active_release").fetchone()
            == before
        )


@pytest.mark.parametrize("candidate", ["missing-release", "release-a"])
def test_promotion_fails_closed_when_candidate_is_missing_or_not_succeeded(candidate: str) -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=ScriptRunOptions(parameters={"release_id": candidate}),
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
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
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
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
            )
        _ = connection.execute("delete from release_results")
        insert_quality_results(connection)
        run_bigquery_script(
            connection,
            PROMOTE,
            options=ScriptRunOptions(parameters={"release_id": "release-b"}),
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
            """insert into release_registry values
            ('release-b', 'failed', date '2024-02-02', null, null)"""
        )
        insert_quality_results(connection)
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE,
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
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
                options=ScriptRunOptions(parameters={"release_id": "release-a"}),
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
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
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
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
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
            options=ScriptRunOptions(parameters={"release_id": "release-b"}),
        )
        run_bigquery_script(connection, ROLLBACK)
        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-a", "release-b")


def test_cleanup_with_null_prior_preserves_active_and_deletes_only_eligible() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            insert into release_registry values
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
