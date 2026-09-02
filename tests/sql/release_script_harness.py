from datetime import UTC, datetime

import duckdb

from tests.sql.bigquery_script_runner import ScriptRunOptions, StatementHook

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
            release_id varchar, status varchar, reference_year integer,
            created_at timestamp, promoted_at timestamp,
            completed_at timestamp, baseline_release_id varchar
        );
        insert into release_registry values
            ('release-a', 'active', 2023, timestamp '2024-01-01',
             timestamp '2024-01-01', current_timestamp, '__bootstrap__'),
            ('release-b', 'succeeded', 2024, timestamp '2024-02-01', null,
             current_timestamp, 'release-a');
        create table release_results(
            release_id varchar,
            rule_id varchar,
            metric_value double,
            severity varchar,
            action varchar,
            details varchar,
            evaluated_at timestamp
        );
        create table release_files(release_id varchar, file_name varchar);
        """
    )
    return connection


def promotion_options(
    release_id: str,
    before_statement: StatementHook | None = None,
) -> ScriptRunOptions:
    return ScriptRunOptions(
        parameters={"release_id": release_id},
        before_statement=before_statement,
    )


def activate_release_b(connection: duckdb.DuckDBPyConnection) -> None:
    _ = connection.execute(
        """
        update active_release
        set release_id = 'release-b', prior_release_id = 'release-a';
        update release_registry set status = 'inactive' where release_id = 'release-a';
        update release_registry set status = 'active' where release_id = 'release-b';
        """
    )


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
    evaluated_at = datetime.now(UTC)
    rows_with_details = [(*row, "test_fixture", evaluated_at) for row in rows]
    _ = connection.executemany(
        "insert into release_results values (?, ?, ?, ?, ?, ?, ?)", rows_with_details
    )
