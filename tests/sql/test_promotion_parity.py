import json
import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    run_bigquery_script,
)
from tests.sql.release_script_harness import (
    MANDATORY_RULES,
    insert_quality_results,
    promotion_options,
    release_database,
)
from tests.sql.test_release_scripts import PROMOTE


def _run_dbt_promotion(database: Path, release_id: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DBT_DUCKDB_PATH"] = str(database)
    return subprocess.run(
        [
            "dbt",
            "run-operation",
            "promote_release",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--target",
            "offline",
            "--args",
            json.dumps({"release_id": release_id}),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_promotion_rejects_a_candidate_in_the_wrong_state() -> None:
    with release_database() as connection:
        _ = connection.execute(
            "update release_registry set status = 'failed' where release_id = 'release-b'"
        )
        insert_quality_results(connection)

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))

        assert connection.execute("select release_id from active_release").fetchone() == (
            "release-a",
        )


def test_promotion_rejects_a_reference_year_regression() -> None:
    with release_database() as connection:
        _ = connection.execute(
            "update release_registry set reference_year = 2022 where release_id = 'release-b'"
        )
        insert_quality_results(connection)

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))

        assert connection.execute("select release_id from active_release").fetchone() == (
            "release-a",
        )


@pytest.mark.parametrize("action", ["block_promotion", "quarantine_and_block"])
def test_promotion_rejects_every_blocking_quality_action(action: str) -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        _ = connection.execute(
            "update release_results set severity='warning',action=? where rule_id='relationships'",
            [action],
        )

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))

        assert connection.execute("select release_id from active_release").fetchone() == (
            "release-a",
        )


def test_promotion_replays_the_same_active_release_without_mutation() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))
        before = connection.execute(
            "select release_id, prior_release_id, promoted_at from active_release"
        ).fetchone()

        run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))

        assert (
            connection.execute(
                "select release_id, prior_release_id, promoted_at from active_release"
            ).fetchone()
            == before
        )
        assert connection.execute(
            "select release_id, status from release_registry order by release_id"
        ).fetchall() == [("release-a", "inactive"), ("release-b", "active")]


def test_active_replay_rejects_duplicate_registry_identity() -> None:
    with release_database() as connection:
        insert_quality_results(connection)
        run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))
        duplicate_identity = """
            insert into release_registry
            select * from release_registry where release_id=?
        """
        _ = connection.execute(duplicate_identity, ["release-b"])

        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(connection, PROMOTE, options=promotion_options("release-b"))

        assert connection.execute(
            "select release_id, prior_release_id from active_release"
        ).fetchone() == ("release-b", "release-a")


@pytest.mark.parametrize("prior_status", [None, "active"])
def test_dbt_promotion_rejects_invalid_prior_registry_lineage(
    tmp_path: Path,
    prior_status: str | None,
) -> None:
    database = tmp_path / "invalid-prior.duckdb"
    prior_id = "batch-202606-y2023-raaaaaaaaaaaa"
    active_id = "batch-202607-y2024-rbbbbbbbbbbbb"
    candidate_id = "batch-202608-y2025-rcccccccccccc"
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            create schema ops; create schema quality;
            create table ops.active_release(singleton_key boolean, release_id varchar,
              prior_release_id varchar, promoted_at timestamp);
            create table ops.release_registry(release_id varchar, status varchar,
              reference_year int, created_at timestamp,
              completed_at timestamp, promoted_at timestamp, baseline_release_id varchar);
            create table quality.release_results(release_id varchar, rule_id varchar,
              metric_value double, severity varchar, action varchar, details varchar,
              evaluated_at timestamp);
            """
        )
        _ = connection.execute(
            "insert into ops.active_release values (true, ?, ?, current_timestamp)",
            [active_id, prior_id],
        )
        _ = connection.execute(
            """
            insert into ops.release_registry values
              (?, 'active', 2024, current_timestamp, current_timestamp,
               current_timestamp, '__bootstrap__'),
              (?, 'succeeded', 2025, current_timestamp, current_timestamp, null, ?)
            """,
            [active_id, candidate_id, active_id],
        )
        if prior_status is not None:
            _ = connection.execute(
                """
                insert into ops.release_registry values
                  (?, ?, 2023, current_timestamp, current_timestamp,
                   current_timestamp, '__bootstrap__')
                """,
                [prior_id, prior_status],
            )
        _ = connection.executemany(
            """
            insert into quality.release_results values
            (?, ?, 0, 'pass', 'promote', 'fixture', current_timestamp)
            """,
            [(candidate_id, rule) for rule in MANDATORY_RULES],
        )

    result = _run_dbt_promotion(database, candidate_id)

    assert result.returncode != 0
    assert (
        "prior release pointer must resolve to exactly one inactive registry row"
        in result.stdout + result.stderr
    )
    with duckdb.connect(str(database), read_only=True) as connection:
        pointer = connection.execute(
            "select release_id, prior_release_id from ops.active_release"
        ).fetchone()
        registry = connection.execute(
            "select release_id, status from ops.release_registry order by release_id"
        ).fetchall()
    assert pointer == (active_id, prior_id)
    assert (active_id, "active") in registry
    assert (candidate_id, "succeeded") in registry
