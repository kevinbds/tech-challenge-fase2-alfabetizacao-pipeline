from pathlib import Path

import duckdb

from tests.dbt.release_macro_support import run_operation
from tests.sql.release_script_harness import MANDATORY_RULES


def test_release_operations_execute_evaluate_bootstrap_promote_and_safe_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "release.duckdb"
    release_id = "batch-202608-y2024-r0123456789ab"
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            create schema ops;
            create schema quality;
            create table ops.active_release(
                singleton_key boolean, release_id varchar,
                prior_release_id varchar, promoted_at timestamp
            );
            insert into ops.active_release values (true, '__bootstrap__', null, current_timestamp);
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
            ('__bootstrap__', 'active', null, current_timestamp,
             null, current_timestamp, null),
            (?, 'succeeded', 2024, current_timestamp, current_timestamp,
             null, '__bootstrap__')
            """,
            [release_id],
        )
        _ = connection.executemany(
            "insert into quality.release_metrics values (?, ?, 0, 'pass', 'promote', 'fixture')",
            [(release_id, rule) for rule in MANDATORY_RULES],
        )

    evaluated = run_operation(
        database,
        "evaluate_release",
        f'{{"release_id":"{release_id}"}}',
    )
    promoted = run_operation(
        database,
        "promote_release",
        f'{{"release_id":"{release_id}"}}',
    )
    replay = run_operation(
        database,
        "promote_release",
        f'{{"release_id":"{release_id}"}}',
    )
    rollback = run_operation(database, "rollback_release", '{"reference_year":2024}')

    assert evaluated.returncode == 0, evaluated.stdout + evaluated.stderr
    assert promoted.returncode == 0, promoted.stdout + promoted.stderr
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert rollback.returncode == 0, rollback.stdout + rollback.stderr
    with duckdb.connect(str(database), read_only=True) as connection:
        pointer = connection.execute(
            "select release_id, prior_release_id from ops.active_release"
        ).fetchone()
        active_rows = connection.execute(
            "select release_id from ops.release_registry where status = 'active'"
        ).fetchall()
        bootstrap_status = connection.execute(
            "select status from ops.release_registry where release_id = '__bootstrap__'"
        ).fetchone()
        result_count = connection.execute(
            "select count(*) from quality.release_results where release_id = ?",
            [release_id],
        ).fetchone()
    assert pointer == (release_id, None)
    assert active_rows == [(release_id,)]
    assert bootstrap_status == ("inactive",)
    assert result_count == (13,)
