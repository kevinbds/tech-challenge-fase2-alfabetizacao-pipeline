from collections.abc import Mapping
from pathlib import Path
from typing import Final

import duckdb

from tests.sql.bigquery_script_runner import ScriptRunOptions, run_bigquery_script

EVALUATE_RELEASE: Final = Path("sql/quality/evaluate_release.sql")
MetricValue = str | int | float

PASSING_METRICS: Final[Mapping[str, MetricValue]] = {
    "required_key_null_rate": 0.0,
    "duplicate_key_rate": 0.0,
    "relationship_rate": 100.0,
    "gold_core_null_rate": 0.0,
    "optional_null_delta_pp": 5.0,
    "out_of_range_rows": 0,
    "negative_rows": 0,
    "invalid_proportion_rows": 0,
    "repeated_rate_percent": 0.01,
    "current_row_count": 80,
    "previous_row_count": 100,
    "days_since_success": 35,
    "identical_copies": 1,
    "identical_payload_hashes": 1,
    "conflicting_payload_variants": 1,
}


def create_quality_database() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    _ = connection.execute(
        """
        create table release_results(
            release_id varchar,
            rule_id varchar,
            metric_value double,
            severity varchar,
            action varchar
        )
        """
    )
    return connection


def persist_quality_results(
    connection: duckdb.DuckDBPyConnection,
    *,
    release_id: str = "release-b",
    overrides: Mapping[str, MetricValue] | None = None,
) -> None:
    metrics = PASSING_METRICS if overrides is None else {**PASSING_METRICS, **overrides}
    run_bigquery_script(
        connection,
        EVALUATE_RELEASE,
        options=ScriptRunOptions(parameters={"release_id": release_id, **metrics}),
    )


def persist_passing_quality_results(
    connection: duckdb.DuckDBPyConnection,
    *,
    release_id: str = "release-b",
) -> None:
    persist_quality_results(connection, release_id=release_id)


def test_evaluate_release_persists_all_catalog_rules_with_exact_decisions() -> None:
    parameters: dict[str, MetricValue] = {
        "release_id": "release-b",
        **PASSING_METRICS,
        "duplicate_key_rate": 0.2,
        "gold_core_null_rate": 0.1,
        "optional_null_delta_pp": 6.0,
        "out_of_range_rows": 2,
        "invalid_proportion_rows": 1,
        "repeated_rate_percent": 0.25,
        "current_row_count": 79,
        "days_since_success": 36,
        "identical_copies": 3,
        "conflicting_payload_variants": 2,
    }
    with create_quality_database() as connection:
        run_bigquery_script(
            connection,
            EVALUATE_RELEASE,
            options=ScriptRunOptions(parameters=parameters),
        )

        actual = connection.execute(
            """
            select rule_id, metric_value, severity, action
            from release_results
            where release_id = 'release-b'
            order by rule_id
            """
        ).fetchall()

    assert actual == [
        ("conflicting_duplicate", 2.0, "critical", "quarantine_and_block"),
        ("gold_core_nulls", 0.1, "critical", "block_promotion"),
        ("identical_duplicate", 3.0, "warning", "deduplicate_and_alert"),
        ("non_negative_measurements", 0.0, "pass", "promote"),
        ("optional_null_delta", 6.0, "warning", "continue_with_alert"),
        ("partition_volume", 21.0, "warning", "continue_with_alert"),
        ("percentage_ranges", 2.0, "critical", "quarantine_and_block"),
        ("pipeline_freshness", 36.0, "critical", "block_promotion"),
        ("proportions_sum", 1.0, "critical", "quarantine_and_block"),
        ("relationships", 100.0, "pass", "promote"),
        ("repeated_evaluation_or_target_rate", 0.25, "warning", "continue_with_alert"),
        ("required_keys", 0.0, "pass", "promote"),
        ("uniqueness_after_quarantine", 0.2, "critical", "quarantine_and_block"),
    ]


def test_evaluate_release_rerun_replaces_the_release_atomically() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "insert into release_results values ('release-b', 'stale', 99, 'critical', 'block')"
        )
        persist_passing_quality_results(connection)
        persist_passing_quality_results(connection)

        actual = connection.execute(
            """
            select count(*), count(distinct rule_id),
                   count(*) filter (where severity = 'pass')
            from release_results where release_id = 'release-b'
            """
        ).fetchone()

    assert actual == (13, 13, 13)
