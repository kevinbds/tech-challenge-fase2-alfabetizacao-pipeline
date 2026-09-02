{{ config(materialized='ephemeral') }}

with expected_relationships as (
    select 'alunos_diretorio_municipio' as relation_name

    union all

    select 'municipio_diretorio'

    union all

    select 'uf_diretorio'

    union all

    select 'meta_municipio_diretorio'

    union all

    select 'meta_uf_diretorio'

    union all

    select 'meta_municipio_resultado'

    union all

    select 'resultado_uf_meta'
),

observed_relationships as (
    select
        relation_name,
        sum(checked_rows) as checked_rows,
        sum(missing_rows) as missing_rows
    from {{ ref('relationship_measurements') }}
    where release_id = '{{ var("release_id") }}'
    group by relation_name
),

relationship_shape as (
    select
        count(*) as actual_relationship_count,
        count(distinct observed.relation_name) as distinct_relationship_count,
        countif(expected.relation_name is null) as unexpected_relationship_count
    from {{ ref('relationship_measurements') }} as observed
    left join expected_relationships as expected
        on observed.relation_name = expected.relation_name
    where observed.release_id = '{{ var("release_id") }}'
),

relationships as (
    select
        shape.actual_relationship_count,
        shape.distinct_relationship_count,
        shape.unexpected_relationship_count,
        sum(coalesce(observed.checked_rows, 0)) as checked_rows,
        sum(coalesce(observed.missing_rows, 0)) as missing_rows,
        count(*) as expected_relationship_count,
        countif(observed.relation_name is null) as missing_expected_relationship_count,
        countif(coalesce(observed.checked_rows, 0) = 0) as empty_relationship_count
    from expected_relationships as expected
    left join observed_relationships as observed
        on expected.relation_name = observed.relation_name
    cross join relationship_shape as shape
    group by all
),

candidate_registry as (
    select
        baseline_release_id,
        reference_year
    from {{ source('ops', 'release_registry') }}
    where release_id = '{{ var("release_id") }}' and status = 'succeeded'
),

gold_core_rows as (
    select
        ano is null or id_municipio is null or id_municipio = ''
        or rede is null or rede = '' or taxa_alfabetizacao is null
        or nome_municipio is null or nome_municipio = '' or sigla_uf is null
        or sigla_uf = '' as invalid,
        false as future_result_missing
    from {{ ref('indicador_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        comparison.ano_meta is null
        or comparison.nivel_geografico is null or comparison.nivel_geografico = ''
        or comparison.id_geografia is null or comparison.id_geografia = ''
        or comparison.nome_geografia is null or comparison.nome_geografia = ''
        or comparison.rede is null or comparison.rede = ''
        or comparison.ano_referencia is null or comparison.meta_alfabetizacao is null
        or case
            when comparison.ano_resultado is null
                then
                    comparison.ano_meta <= registry.reference_year
                    or comparison.taxa_resultado is not null
                    or comparison.gap_pp is not null or comparison.status_meta is not null
            else
                comparison.ano_resultado != comparison.ano_meta
                or comparison.taxa_resultado is null
                or comparison.gap_pp is null or comparison.status_meta is null
        end as invalid,
        comparison.ano_meta > registry.reference_year
        and comparison.ano_resultado is null and comparison.taxa_resultado is null
        and comparison.gap_pp is null and comparison.status_meta is null
            as future_result_missing
    from {{ ref('comparativo_meta_resultado') }} as comparison
    cross join candidate_registry as registry
    where comparison.release_id = '{{ var("release_id") }}'
),

gold_core as (
    select
        count(*) as row_count,
        countif(invalid) as null_count,
        countif(future_result_missing) as future_null_count
    from gold_core_rows
),

optional_rates as (
    select
        countif(m.release_id = '{{ var("release_id") }}') as target_rows,
        countif(m.release_id = '{{ var("release_id") }}' and m.media_portugues is null)
            as target_nulls,
        countif(m.release_id = registry.baseline_release_id) as baseline_rows,
        countif(
            m.release_id = registry.baseline_release_id and m.media_portugues is null
        ) as baseline_nulls
    from {{ ref('silver_municipio') }} as m
    cross join candidate_registry as registry
),

measurement_violations as (
    select
        countif(
            media_portugues < 0 or taxa_alfabetizacao < 0
            {% for level in range(9) %}
                or proporcao_aluno_nivel_{{ level }} < 0
            {% endfor %}
        ) as invalid_count
    from {{ ref('silver_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            media_portugues < 0 or taxa_alfabetizacao < 0
            {% for level in range(9) %}
                or proporcao_aluno_nivel_{{ level }} < 0
            {% endfor %}
        ) as invalid_count
    from {{ ref('silver_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select countif(proficiencia < 0 or peso_aluno < 0) as invalid_count
    from {{ ref('silver_alunos') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            {% for year in range(2024, 2031) %}
                or meta_alfabetizacao_{{ year }} < 0
            {% endfor %}
        ) as invalid_count
    from {{ ref('silver_meta_alfabetizacao_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            {% for year in range(2024, 2031) %}
                or meta_alfabetizacao_{{ year }} < 0
            {% endfor %}
        ) as invalid_count
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            {% for year in range(2024, 2031) %}
                or meta_alfabetizacao_{{ year }} < 0
            {% endfor %}
        ) as invalid_count
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
)

select
    relationships.checked_rows,
    relationships.missing_rows,
    relationships.expected_relationship_count,
    relationships.actual_relationship_count,
    relationships.distinct_relationship_count,
    relationships.missing_expected_relationship_count,
    relationships.empty_relationship_count,
    relationships.unexpected_relationship_count,
    gold_core.row_count as gold_row_count,
    gold_core.null_count as gold_null_count,
    gold_core.future_null_count as gold_future_null_count,
    optional_rates.baseline_rows,
    100.0 * optional_rates.target_nulls / nullif(optional_rates.target_rows, 0)
    - 100.0 * optional_rates.baseline_nulls / nullif(optional_rates.baseline_rows, 0)
        as optional_null_delta,
    sum(measurement_violations.invalid_count) as invalid_measurements
from relationships
cross join gold_core
cross join optional_rates
cross join measurement_violations
group by all
