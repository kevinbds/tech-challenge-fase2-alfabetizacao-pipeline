from pathlib import Path

import duckdb
import pytest

HARNESS = Path("sql/quality/local_medallion_harness.sql")


@pytest.fixture
def warehouse() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    _ = connection.execute(HARNESS.read_text(encoding="utf-8"))
    return connection


def test_gold_grains_and_exact_values(warehouse: duckdb.DuckDBPyConnection) -> None:
    indicator = warehouse.execute(
        """
        select ano, id_municipio, rede, taxa_alfabetizacao, nome_municipio
        from gold_indicador_municipio order by ano, id_municipio, rede
        """
    ).fetchall()
    assert indicator == [
        (2023, "3304557", "estadual", 70.0, "Rio de Janeiro"),
        (2023, "3550308", "municipal", 60.0, "São Paulo"),
        (2024, "3304557", "estadual", 73.0, "Rio de Janeiro"),
        (2024, "3550308", "municipal", 68.0, "São Paulo"),
    ]
    assert warehouse.execute(
        "select count(*) = count(distinct (ano, id_municipio, rede)) from gold_indicador_municipio"
    ).fetchone() == (True,)


def test_reference_choice_gap_status_and_null_unpivot(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    actual = warehouse.execute(
        """
        select ano_resultado, id_geografia, rede, ano_referencia, meta_alfabetizacao,
               taxa_resultado, gap_pp, status_meta
        from gold_comparativo_meta_resultado order by id_geografia
        """
    ).fetchall()
    assert actual == [
        (2024, "3304557", "estadual", 2023, 72.0, 73.0, 1.0, "atingida"),
        (2024, "3550308", "municipal", 2024, 67.0, 68.0, 1.0, "atingida"),
    ]
    assert warehouse.execute(
        "select count(*) from gold_comparativo_meta_resultado where meta_alfabetizacao is null"
    ).fetchone() == (0,)


def test_evolution_lag_and_hybrid_overlay_tie_break(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    evolution = warehouse.execute(
        """
        select ano, id_municipio, rede, taxa_alfabetizacao, taxa_ano_anterior, variacao_pp
        from gold_evolucao_alfabetizacao where ano = 2024 order by id_municipio
        """
    ).fetchall()
    assert evolution == [
        (2024, "3304557", "estadual", 73.0, 70.0, 3.0),
        (2024, "3550308", "municipal", 68.0, 60.0, 8.0),
    ]
    hybrid = warehouse.execute(
        """
        select id_municipio, rede, taxa_alfabetizacao, origem
        from gold_indicador_atual_hibrido order by id_municipio
        """
    ).fetchall()
    assert hybrid == [
        ("3304557", "estadual", 73.0, "batch_oficial"),
        ("3550308", "municipal", 72.0, "stream_simulacao"),
    ]


def test_duplicate_classification_and_quality_actions(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    assert warehouse.execute(
        "select event_id, duplicate_kind from audit_duplicates order by event_id"
    ).fetchall() == [("evt-conflict", "conflicting"), ("evt-same", "identical")]
    assert warehouse.execute(
        "select rule_id, severity, action from quality_results order by rule_id"
    ).fetchall() == [
        ("repeated_rate_critical", "critical", "quarantine_and_block"),
        ("volume_warning", "warning", "continue_with_alert"),
    ]


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(0.01, "pass"), (0.0101, "warning"), (0.50, "warning"), (0.5001, "critical")],
)
def test_repeated_rate_threshold_edges(rate: float, expected: str) -> None:
    connection = duckdb.connect(":memory:")
    actual = connection.execute(
        "select case when ? <= 0.01 then 'pass' when ? <= 0.50 then 'warning' else 'critical' end",
        [rate, rate],
    ).fetchone()
    assert actual == (expected,)


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (80, 100, "pass"),
        (79, 100, "warning"),
        (50, 100, "warning"),
        (49, 100, "critical"),
        (0, 100, "critical"),
    ],
)
def test_volume_threshold_edges(current: int, previous: int, expected: str) -> None:
    connection = duckdb.connect(":memory:")
    query = """select case when ? = 0 or ? < ? * 0.5 then 'critical'
        when abs(? - ?) > ? * 0.2 then 'warning' else 'pass' end"""
    actual = connection.execute(
        query,
        [current, current, previous, current, previous, previous],
    ).fetchone()
    assert actual == (expected,)


def test_student_parent_relationship_is_release_scoped(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    assert warehouse.execute("select * from orphan_students").fetchall() == [
        ("release-b", 2024, "9999999", "municipal", "student-synthetic-2"),
    ]


def test_promotion_failure_rolls_back_and_cleanup_excludes_protected_releases() -> None:
    connection = duckdb.connect(":memory:")
    _ = connection.execute(
        """
        create table active_release(singleton_key boolean primary key, release_id varchar);
        insert into active_release values (true, 'release-a');
        create table release_history(release_id varchar, prior_release_id varchar, status varchar,
                                     created_at timestamp);
        insert into release_history values
          ('release-a', null, 'succeeded', current_timestamp - interval 45 day),
          ('release-b', 'release-a', 'succeeded', current_timestamp - interval 40 day),
          ('release-c', 'release-b', 'failed', current_timestamp - interval 8 day),
          ('release-d', 'release-b', 'succeeded', current_timestamp - interval 31 day);
        """
    )
    _ = connection.execute("begin transaction")
    assert connection.execute(
        "select count(*) from active_release where singleton_key"
    ).fetchone() == (1,)
    _ = connection.execute("update active_release set release_id = 'release-b' where singleton_key")
    _ = connection.execute("commit")
    assert connection.execute("select release_id from active_release").fetchone() == ("release-b",)

    _ = connection.execute("begin transaction")
    _ = connection.execute("insert into active_release values (false, 'corrupt')")
    cardinality = connection.execute("select count(*) from active_release").fetchone()
    assert cardinality == (2,)
    _ = connection.execute("rollback")
    remaining_releases = connection.execute("select release_id from active_release").fetchall()
    assert remaining_releases == [("release-b",)]

    cleanup = connection.execute(
        """
        select release_id from release_history
        where ((status = 'failed' and created_at < current_timestamp - interval 7 day)
           or (status = 'succeeded' and created_at < current_timestamp - interval 30 day))
          and release_id not in (
            select release_id from active_release
            union all
            select prior_release_id from release_history
            where release_id = (select release_id from active_release)
          )
        order by release_id
        """
    ).fetchall()
    assert cleanup == [("release-c",), ("release-d",)]
