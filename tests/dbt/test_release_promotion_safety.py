from pathlib import Path
from typing import TYPE_CHECKING, cast

import duckdb
import pytest
from jinja2 import Environment

from tests.dbt.release_macro_support import (
    CompilerErrors,
    QueryResult,
    identity,
    macro_source,
)
from tests.sql.bigquery_script_runner import ScriptAssertionError, run_bigquery_script
from tests.sql.release_script_harness import MANDATORY_RULES

if TYPE_CHECKING:
    from collections.abc import Callable


def test_bigquery_promotion_rejects_a_dangling_prior_before_mutation(tmp_path: Path) -> None:
    database = tmp_path / "bigquery-macro.duckdb"
    prior_id = "batch-202606-y2023-raaaaaaaaaaaa"
    active_id = "batch-202607-y2024-rbbbbbbbbbbbb"
    candidate_id = "batch-202608-y2025-rcccccccccccc"
    with duckdb.connect(str(database)) as connection:
        _ = connection.execute(
            """
            create schema ops;
            create schema quality;
            create table ops.active_release(
                singleton_key boolean, release_id varchar,
                prior_release_id varchar, promoted_at timestamp
            );
            create table ops.release_registry(
                release_id varchar, status varchar, reference_year int,
                created_at timestamp, completed_at timestamp,
                promoted_at timestamp, baseline_release_id varchar
            );
            create table quality.release_results(
                release_id varchar, rule_id varchar, metric_value double,
                severity varchar, action varchar, details varchar, evaluated_at timestamp
            );
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
        _ = connection.executemany(
            """
            insert into quality.release_results values
            (?, ?, 0, 'pass', 'promote', 'fixture', current_timestamp)
            """,
            [(candidate_id, rule) for rule in MANDATORY_RULES],
        )
        captured_sql: list[str] = []

        def run_query(sql: str) -> QueryResult:
            captured_sql.append(sql)
            return QueryResult()

        def source(schema: str, table: str) -> str:
            return f"{schema}.{table}"

        def ref(model: str) -> str:
            return f"quality.{model}"

        module = (
            Environment(autoescape=True, extensions=["jinja2.ext.do"])
            .from_string(macro_source("release_promotion_bigquery.sql"))
            .make_module(
                {
                    "run_query": run_query,
                    "source": source,
                    "ref": ref,
                    "exceptions": CompilerErrors(),
                    "return": identity,
                },
            )
        )
        promote = cast(
            "Callable[[str], str]",
            module.__dict__["bigquery__promote_release"],
        )
        _ = promote(candidate_id)
        rendered = tmp_path / "bigquery_macro.sql"
        _ = rendered.write_text(captured_sql[0], encoding="utf-8")

        with pytest.raises(
            ScriptAssertionError,
            match="prior release pointer must resolve to exactly one inactive registry row",
        ):
            run_bigquery_script(connection, rendered)

        pointer = connection.execute(
            "select release_id, prior_release_id from ops.active_release"
        ).fetchone()
        registry = connection.execute(
            "select release_id, status from ops.release_registry order by release_id"
        ).fetchall()
    assert pointer == (active_id, prior_id)
    assert registry == [(active_id, "active"), (candidate_id, "succeeded")]


def test_duckdb_promotion_stops_before_registry_updates_when_the_pointer_is_stale() -> None:
    active_id = "batch-202607-y2024-rbbbbbbbbbbbb"
    prior_id = "batch-202606-y2023-raaaaaaaaaaaa"
    candidate_id = "batch-202608-y2025-rcccccccccccc"
    responses = iter(
        [
            QueryResult((1,)),
            QueryResult((active_id, prior_id)),
            QueryResult((1, 1)),
            QueryResult((1, 1)),
            QueryResult((1,)),
            QueryResult((0,)),
            QueryResult((1,)),
            QueryResult((13, 13, 0, 0)),
            QueryResult(),
            QueryResult(row_count=0),
            QueryResult(),
        ]
    )
    statements: list[str] = []

    def run_query(sql: str) -> QueryResult:
        statements.append(" ".join(sql.split()))
        return next(responses)

    module = (
        Environment(autoescape=True, extensions=["jinja2.ext.do"])
        .from_string(macro_source("release_promotion_duckdb.sql"))
        .make_module(
            {"run_query": run_query, "exceptions": CompilerErrors(), "return": identity},
        )
    )
    promote = cast(
        "Callable[[str], str]",
        module.__dict__["duckdb__promote_release"],
    )

    with pytest.raises(RuntimeError, match="active release changed during promotion"):
        _ = promote(candidate_id)

    assert statements[-1] == "rollback"
    assert not any(statement.startswith("update ops.release_registry") for statement in statements)
