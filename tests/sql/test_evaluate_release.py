from pathlib import Path
from typing import Final

import duckdb
import pytest

from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.dbt_model_runner import materialize_dbt_model

EVALUATE_RELEASE: Final = Path("sql/quality/evaluate_release.sql")
PROMOTE_RELEASE: Final = Path("sql/quality/promote_release.sql")
RELEASE_METRICS: Final = Path("dbt/models/quality/release_metrics.sql")
RELEASE_PERCENTAGE_METRICS: Final = Path("dbt/models/quality/release_percentage_metrics.sql")
PROPORTION_FIELDS: Final = tuple(f"proporcao_aluno_nivel_{level}" for level in range(9))


def _null_update(table: str, column: str) -> str:
    update = "update"
    return f"{update} {table} set {column} = null where release_id = 'release-b'"


REQUIRED_NULL_CASES: Final = (
    *(
        (
            _null_update(table, "taxa_alfabetizacao"),
            ("percentage_ranges",),
        )
        for table in ("silver_municipio", "silver_uf")
    ),
    *(
        (
            _null_update(table, field),
            ("percentage_ranges", "proportions_sum"),
        )
        for table in ("silver_municipio", "silver_uf")
        for field in PROPORTION_FIELDS
    ),
    *(
        (
            _null_update(table, field),
            ("percentage_ranges",),
        )
        for table in (
            "silver_meta_alfabetizacao_municipio",
            "silver_meta_alfabetizacao_uf",
            "silver_meta_alfabetizacao_brasil",
        )
        for field in ("taxa_alfabetizacao", "percentual_participacao")
    ),
    (
        _null_update("indicador_municipio", "taxa_alfabetizacao"),
        ("gold_core_nulls",),
    ),
    (
        _null_update("comparativo_meta_resultado", "taxa_resultado"),
        ("gold_core_nulls",),
    ),
    (
        _null_update("comparativo_meta_resultado", "meta_alfabetizacao"),
        ("gold_core_nulls",),
    ),
)
OPTIONAL_TARGET_NULL_SQL: Final = tuple(
    _null_update(table, f"meta_alfabetizacao_{year}")
    for table in (
        "silver_meta_alfabetizacao_municipio",
        "silver_meta_alfabetizacao_uf",
        "silver_meta_alfabetizacao_brasil",
    )
    for year in range(2024, 2031)
)


def install_release_data(connection: duckdb.DuckDBPyConnection) -> None:
    _ = connection.execute(
        """
        create table silver_municipio(
            release_id varchar, ano int, id_municipio varchar, rede varchar,
            taxa_alfabetizacao double, media_portugues double,
            proporcao_aluno_nivel_0 double, proporcao_aluno_nivel_1 double,
            proporcao_aluno_nivel_2 double, proporcao_aluno_nivel_3 double,
            proporcao_aluno_nivel_4 double, proporcao_aluno_nivel_5 double,
            proporcao_aluno_nivel_6 double, proporcao_aluno_nivel_7 double,
            proporcao_aluno_nivel_8 double
        );
        insert into silver_municipio values
            ('release-a', 2024, '3550308', 'municipal', 70, 200,
             10, 10, 10, 10, 10, 10, 10, 10, 20),
            ('release-b', 2024, '3550308', 'municipal', 72, 205,
             10, 10, 10, 10, 10, 10, 10, 10, 20);
        create table silver_uf as select
            release_id, ano, 'SP'::varchar as sigla_uf, rede,
            taxa_alfabetizacao, media_portugues,
            proporcao_aluno_nivel_0, proporcao_aluno_nivel_1,
            proporcao_aluno_nivel_2, proporcao_aluno_nivel_3,
            proporcao_aluno_nivel_4, proporcao_aluno_nivel_5,
            proporcao_aluno_nivel_6, proporcao_aluno_nivel_7,
            proporcao_aluno_nivel_8
        from silver_municipio;
        create table silver_meta_alfabetizacao_municipio as select
            release_id, ano, id_municipio, rede, taxa_alfabetizacao,
            90::double as percentual_participacao,
            70::double as meta_alfabetizacao_2024,
            71::double as meta_alfabetizacao_2025,
            72::double as meta_alfabetizacao_2026,
            73::double as meta_alfabetizacao_2027,
            74::double as meta_alfabetizacao_2028,
            75::double as meta_alfabetizacao_2029,
            76::double as meta_alfabetizacao_2030
        from silver_municipio;
        create table silver_meta_alfabetizacao_uf as select
            release_id, ano, 'SP'::varchar as sigla_uf, rede,
            taxa_alfabetizacao, percentual_participacao,
            meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027,
            meta_alfabetizacao_2028, meta_alfabetizacao_2029,
            meta_alfabetizacao_2030
        from silver_meta_alfabetizacao_municipio;
        create table silver_meta_alfabetizacao_brasil as select
            release_id, ano, rede, taxa_alfabetizacao, percentual_participacao,
            meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027,
            meta_alfabetizacao_2028, meta_alfabetizacao_2029,
            meta_alfabetizacao_2030
        from silver_meta_alfabetizacao_municipio;
        create table silver_alunos(
            release_id varchar, ano int, id_municipio varchar, id_escola varchar,
            id_aluno varchar, rede varchar, proficiencia double, peso_aluno double
        );
        insert into silver_alunos values
            ('release-a', 2024, '3550308', 'school-1', 'student-a', 'municipal', 200, 1),
            ('release-b', 2024, '3550308', 'school-1', 'student-b', 'municipal', 210, 1);
        create table stg_alunos as select * from silver_alunos;
        create table indicador_municipio as select
            release_id, ano, id_municipio, rede, taxa_alfabetizacao,
            'Sao Paulo'::varchar as nome_municipio, 'SP'::varchar as sigla_uf
        from silver_municipio;
        create table comparativo_meta_resultado as select
            release_id, ano as ano_resultado, 'municipio'::varchar as nivel_geografico,
            id_municipio as id_geografia, rede, taxa_alfabetizacao as taxa_resultado,
            70::double as meta_alfabetizacao
        from silver_municipio;
        create table audit_identical_duplicates(release_id varchar, copies int);
        create table quarantine_conflicting_duplicates(
            release_id varchar, business_key_hash varchar, row_hash varchar
        );
        """
    )


def create_quality_database() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    _ = connection.execute(
        """
        create table active_release(
            singleton_key boolean, release_id varchar, prior_release_id varchar,
            promoted_at timestamp
        );
        insert into active_release values (true, 'release-a', null, current_timestamp);
        create table release_registry(
            release_id varchar, status varchar, created_at timestamp,
            promoted_at timestamp, completed_at timestamp
        );
        insert into release_registry values
            ('release-a', 'active', current_timestamp, current_timestamp, current_timestamp),
            ('release-b', 'succeeded', current_timestamp, null, current_timestamp);
        create table release_results(
            release_id varchar, rule_id varchar, metric_value double,
            severity varchar, action varchar, details varchar
        );
        """
    )
    install_release_data(connection)
    return connection


def persist_quality_results(
    connection: duckdb.DuckDBPyConnection, *, release_id: str = "release-b"
) -> None:
    tables = connection.execute(
        "select count(*) from information_schema.tables where table_name = 'silver_municipio'"
    ).fetchone()
    if tables == (0,):
        install_release_data(connection)
    parameters = {"release_id": release_id}
    materialize_dbt_model(
        connection,
        RELEASE_PERCENTAGE_METRICS,
        "release_percentage_metrics",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_METRICS,
        "release_metrics",
        parameters,
    )
    run_bigquery_script(
        connection,
        EVALUATE_RELEASE,
        options=ScriptRunOptions(parameters=parameters),
    )


def persist_passing_quality_results(
    connection: duckdb.DuckDBPyConnection, *, release_id: str = "release-b"
) -> None:
    persist_quality_results(connection, release_id=release_id)


def test_evaluator_calculates_exact_catalog_from_release_tables() -> None:
    with create_quality_database() as connection:
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select count(*), count(distinct rule_id),
                   count(*) filter (where severity = 'critical')
            from release_results where release_id = 'release-b'
            """
        ).fetchone()
        repeated = connection.execute(
            """
            select metric_value, severity, details from release_results
            where rule_id = 'repeated_evaluation_or_target_rate'
            """
        ).fetchone()
    assert actual == (13, 13, 0)
    assert repeated == (0.0, "pass", "stg_alunos_pre_deduplication")


def test_source_defects_change_measured_results_without_metric_parameters() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "insert into stg_alunos select * from stg_alunos where release_id = 'release-b'"
        )
        _ = connection.execute(
            "update silver_municipio set taxa_alfabetizacao = 101 where release_id = 'release-b'"
        )
        _ = connection.execute(
            """update silver_meta_alfabetizacao_brasil
            set meta_alfabetizacao_2030 = -1 where release_id = 'release-b'"""
        )
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select rule_id, severity from release_results
            where rule_id in (
                'non_negative_measurements', 'percentage_ranges',
                'repeated_evaluation_or_target_rate'
            )
            order by rule_id
            """
        ).fetchall()
    assert actual == [
        ("non_negative_measurements", "critical"),
        ("percentage_ranges", "critical"),
        ("repeated_evaluation_or_target_rate", "critical"),
    ]


def test_missing_baseline_is_an_explicit_warning() -> None:
    with create_quality_database() as connection:
        _ = connection.execute("update active_release set release_id = 'missing-baseline'")
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select rule_id, severity, details from release_results
            where rule_id in ('optional_null_delta', 'partition_volume')
            order by rule_id
            """
        ).fetchall()
    assert actual == [
        ("optional_null_delta", "warning", "baseline_missing"),
        ("partition_volume", "warning", "baseline_missing"),
    ]


@pytest.mark.parametrize(("defect_sql", "critical_rules"), REQUIRED_NULL_CASES)
def test_required_percentage_null_is_critical_and_blocks_promotion(
    defect_sql: str, critical_rules: tuple[str, ...]
) -> None:
    with create_quality_database() as connection:
        _ = connection.execute(defect_sql)
        persist_quality_results(connection)
        actual = connection.execute(
            "select rule_id from release_results where severity = 'critical' order by rule_id"
        ).fetchall()
        assert actual == [(rule,) for rule in sorted(critical_rules)]
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE_RELEASE,
                options=ScriptRunOptions(parameters={"release_id": "release-b"}),
            )


def test_optional_mean_and_unselected_annual_targets_do_not_become_critical() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "update silver_municipio set media_portugues = null where release_id = 'release-b'"
        )
        for update_sql in OPTIONAL_TARGET_NULL_SQL:
            _ = connection.execute(update_sql)
        persist_quality_results(connection)
        assert connection.execute(
            "select count(*) from release_results where severity = 'critical'"
        ).fetchone() == (0,)
        assert connection.execute(
            "select severity, details from release_results where rule_id = 'optional_null_delta'"
        ).fetchone() == ("warning", "media_portugues_pp_delta")
        run_bigquery_script(
            connection,
            PROMOTE_RELEASE,
            options=ScriptRunOptions(parameters={"release_id": "release-b"}),
        )
