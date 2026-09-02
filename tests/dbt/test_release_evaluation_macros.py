import json
from pathlib import Path

import duckdb

from tests.dbt.release_macro_support import run_operation
from tests.sql.release_script_harness import MANDATORY_RULES


def test_evaluate_release_keeps_existing_results_when_candidate_state_is_invalid(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evaluate-invalid-state.duckdb"
    release_id = "batch-202608-y2024-r0123456789ab"
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            create schema ops;
            create schema quality;
            create table ops.release_registry(
                release_id varchar, status varchar, reference_year int,
                created_at timestamp, completed_at timestamp,
                promoted_at timestamp, baseline_release_id varchar
            );
            create table quality.release_metrics(
                release_id varchar, rule_id varchar, metric_value double,
                severity varchar, action varchar, details varchar
            );
            create table quality.release_results(
                release_id varchar, rule_id varchar, metric_value double,
                severity varchar, action varchar, details varchar, evaluated_at timestamp
            );
            """
        )
        _ = connection.execute(
            """
            insert into ops.release_registry values
            (?, 'failed', 2024, current_timestamp, current_timestamp, null, '__bootstrap__')
            """,
            [release_id],
        )
        _ = connection.execute(
            """
            insert into quality.release_results values
            (?, 'existing_evidence', 7, 'pass', 'promote', 'preserve', current_timestamp)
            """,
            [release_id],
        )

    result = run_operation(
        database,
        "evaluate_release",
        json.dumps({"release_id": release_id}),
    )

    assert result.returncode != 0
    assert "candidate state or baseline differs" in result.stdout + result.stderr
    with duckdb.connect(str(database), read_only=True) as connection:
        preserved = connection.execute(
            """
            select rule_id, metric_value, details
            from quality.release_results
            where release_id = ?
            """,
            [release_id],
        ).fetchall()
    assert preserved == [("existing_evidence", 7.0, "preserve")]


def test_release_operations_reject_untrusted_identifiers_before_querying(
    tmp_path: Path,
) -> None:
    database = tmp_path / "empty.duckdb"
    malicious_release = run_operation(
        database,
        "evaluate_release",
        json.dumps(
            {
                "release_id": "batch-202608-y2024-r01234567';drop table x;--",
            }
        ),
    )

    assert malicious_release.returncode != 0
    assert "invalid release_id" in malicious_release.stdout + malicious_release.stderr


def test_promotion_rejects_a_candidate_older_than_the_active_release(tmp_path: Path) -> None:
    database = tmp_path / "annual-order.duckdb"
    active_id = "batch-202608-y2025-r111111111111"
    candidate_id = "batch-202608-y2024-r222222222222"
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
            "insert into ops.active_release values (true, ?, null, current_timestamp)",
            [active_id],
        )
        _ = connection.execute(
            """
            insert into ops.release_registry values
              (?, 'active', 2025, current_timestamp, current_timestamp,
               current_timestamp, '__bootstrap__'),
              (?, 'succeeded', 2024, current_timestamp, current_timestamp,
               null, ?)
            """,
            [active_id, candidate_id, active_id],
        )
        _ = connection.executemany(
            """
            insert into quality.release_results values
            (?, ?, 0, 'pass', 'promote', 'fixture', current_timestamp)
            """,
            [(candidate_id, rule) for rule in MANDATORY_RULES],
        )

    result = run_operation(
        database,
        "promote_release",
        f'{{"release_id":"{candidate_id}"}}',
    )

    assert result.returncode != 0
    assert "candidate state or quality baseline differs" in result.stdout + result.stderr
