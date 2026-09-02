from pathlib import Path
from typing import Final

import duckdb

from tests.sql.bigquery_script_runner import ScriptRunOptions, run_bigquery_script
from tests.sql.dbt_model_runner import materialize_dbt_model

EVALUATE_RELEASE: Final = Path("sql/quality/evaluate_release.sql")
RELEASE_METRICS: Final = Path("dbt/models/quality/release_metrics.sql")
RELEASE_QUALITY_CORE: Final = Path("dbt/models/quality/release_quality_core.sql")
RELEASE_QUALITY_KEY_COVERAGE: Final = Path("dbt/models/quality/release_quality_key_coverage.sql")
RELEASE_QUALITY_MEASUREMENTS: Final = Path("dbt/models/quality/release_quality_measurements.sql")
RELEASE_QUALITY_OPERATIONAL: Final = Path("dbt/models/quality/release_quality_operational.sql")
RELEASE_VOLUME_METRIC: Final = Path("dbt/models/quality/release_volume_metric.sql")
RELEASE_PERCENTAGE_METRICS: Final = Path("dbt/models/quality/release_percentage_metrics.sql")
RELATIONSHIP_MEASUREMENTS: Final = Path("dbt/models/quality/relationship_measurements.sql")


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
            release_id, ano, 'SP'::varchar as sigla_uf, 'publica'::varchar as rede,
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
            release_id, ano, 'SP'::varchar as sigla_uf, 'publica'::varchar as rede,
            taxa_alfabetizacao, percentual_participacao,
            meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027,
            meta_alfabetizacao_2028, meta_alfabetizacao_2029,
            meta_alfabetizacao_2030
        from silver_meta_alfabetizacao_municipio;
        create table silver_meta_alfabetizacao_brasil as select
            release_id, ano, 'publica'::varchar as rede, taxa_alfabetizacao,
            percentual_participacao,
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
        create table municipio(id_municipio varchar, nome varchar, sigla_uf varchar);
        insert into municipio values ('3550308', 'Sao Paulo', 'SP');
        create table stg_alunos as select * from silver_alunos;
        create table indicador_municipio as select
            release_id, ano, id_municipio, rede, taxa_alfabetizacao,
            'Sao Paulo'::varchar as nome_municipio, 'SP'::varchar as sigla_uf
        from silver_municipio;
        create table comparativo_meta_resultado as
        select
            release_id,
            ano as ano_meta,
            ano as ano_resultado,
            'municipio'::varchar as nivel_geografico,
            id_municipio as id_geografia,
            'Sao Paulo'::varchar as nome_geografia,
            rede,
            ano as ano_referencia,
            70::double as meta_alfabetizacao,
            taxa_alfabetizacao as taxa_resultado,
            taxa_alfabetizacao - 70::double as gap_pp,
            'atingida'::varchar as status_meta
        from silver_municipio;
        create table audit_identical_duplicates(release_id varchar, copies int);
        create table quarantine_conflicting_duplicates(
            release_id varchar, business_key_hash varchar, row_hash varchar
        );
        create table quarantine_meta_alfabetizacao_uf(
            release_id varchar, ano int, sigla_uf varchar, rede varchar,
            source_run_id varchar, ingested_at timestamp, source_table varchar,
            reason_code varchar
        );
        drop table if exists release_files;
        create table release_files(
            release_id varchar, table_name varchar, row_count int,
            status varchar, ingested_at timestamp, verified_at timestamp
        );
        insert into release_files
        select 'release-b', source, 1, 'selected', current_timestamp, current_timestamp
        from (values
            ('uf'), ('meta_alfabetizacao_brasil'), ('meta_alfabetizacao_uf'),
            ('meta_alfabetizacao_municipio'), ('municipio'), ('alunos')
        ) as expected(source);
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
            promoted_at timestamp, completed_at timestamp,
            baseline_release_id varchar, reference_year int
        );
        insert into release_registry values
            (
                'release-a', 'active', current_timestamp, current_timestamp,
                current_timestamp, null, 2024
            ),
            (
                'release-b', 'succeeded', current_timestamp, null,
                current_timestamp, 'release-a', 2024
            );
        create table release_results(
            release_id varchar, rule_id varchar, metric_value double,
            severity varchar, action varchar, details varchar, evaluated_at timestamp
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
        RELATIONSHIP_MEASUREMENTS,
        "relationship_measurements",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_VOLUME_METRIC,
        "release_volume_metric",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_QUALITY_KEY_COVERAGE,
        "release_quality_key_coverage",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_QUALITY_MEASUREMENTS,
        "release_quality_measurements",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_QUALITY_CORE,
        "release_quality_core",
        parameters,
    )
    materialize_dbt_model(
        connection,
        RELEASE_QUALITY_OPERATIONAL,
        "release_quality_operational",
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
