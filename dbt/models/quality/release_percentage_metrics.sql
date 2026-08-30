{{ config(materialized='table', schema='quality', alias='release_percentage_metrics') }}

with range_rows as (
    select
        taxa_alfabetizacao is null or taxa_alfabetizacao not between 0 and 100
        or proporcao_aluno_nivel_0 is null or proporcao_aluno_nivel_0 not between 0 and 100
        or proporcao_aluno_nivel_1 is null or proporcao_aluno_nivel_1 not between 0 and 100
        or proporcao_aluno_nivel_2 is null or proporcao_aluno_nivel_2 not between 0 and 100
        or proporcao_aluno_nivel_3 is null or proporcao_aluno_nivel_3 not between 0 and 100
        or proporcao_aluno_nivel_4 is null or proporcao_aluno_nivel_4 not between 0 and 100
        or proporcao_aluno_nivel_5 is null or proporcao_aluno_nivel_5 not between 0 and 100
        or proporcao_aluno_nivel_6 is null or proporcao_aluno_nivel_6 not between 0 and 100
        or proporcao_aluno_nivel_7 is null or proporcao_aluno_nivel_7 not between 0 and 100
        or proporcao_aluno_nivel_8 is null
        or proporcao_aluno_nivel_8 not between 0 and 100 as invalid
    from {{ ref('silver_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        taxa_alfabetizacao is null or taxa_alfabetizacao not between 0 and 100
        or proporcao_aluno_nivel_0 is null or proporcao_aluno_nivel_0 not between 0 and 100
        or proporcao_aluno_nivel_1 is null or proporcao_aluno_nivel_1 not between 0 and 100
        or proporcao_aluno_nivel_2 is null or proporcao_aluno_nivel_2 not between 0 and 100
        or proporcao_aluno_nivel_3 is null or proporcao_aluno_nivel_3 not between 0 and 100
        or proporcao_aluno_nivel_4 is null or proporcao_aluno_nivel_4 not between 0 and 100
        or proporcao_aluno_nivel_5 is null or proporcao_aluno_nivel_5 not between 0 and 100
        or proporcao_aluno_nivel_6 is null or proporcao_aluno_nivel_6 not between 0 and 100
        or proporcao_aluno_nivel_7 is null or proporcao_aluno_nivel_7 not between 0 and 100
        or proporcao_aluno_nivel_8 is null or proporcao_aluno_nivel_8 not between 0 and 100
    from {{ ref('silver_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        taxa_alfabetizacao is null or taxa_alfabetizacao not between 0 and 100
        or percentual_participacao is null or percentual_participacao not between 0 and 100
        or meta_alfabetizacao_2024 not between 0 and 100
        or meta_alfabetizacao_2025 not between 0 and 100
        or meta_alfabetizacao_2026 not between 0 and 100
        or meta_alfabetizacao_2027 not between 0 and 100
        or meta_alfabetizacao_2028 not between 0 and 100
        or meta_alfabetizacao_2029 not between 0 and 100
        or meta_alfabetizacao_2030 not between 0 and 100
    from {{ ref('silver_meta_alfabetizacao_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        taxa_alfabetizacao is null or taxa_alfabetizacao not between 0 and 100
        or percentual_participacao is null or percentual_participacao not between 0 and 100
        or meta_alfabetizacao_2024 not between 0 and 100
        or meta_alfabetizacao_2025 not between 0 and 100
        or meta_alfabetizacao_2026 not between 0 and 100
        or meta_alfabetizacao_2027 not between 0 and 100
        or meta_alfabetizacao_2028 not between 0 and 100
        or meta_alfabetizacao_2029 not between 0 and 100
        or meta_alfabetizacao_2030 not between 0 and 100
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        taxa_alfabetizacao is null or taxa_alfabetizacao not between 0 and 100
        or percentual_participacao is null or percentual_participacao not between 0 and 100
        or meta_alfabetizacao_2024 not between 0 and 100
        or meta_alfabetizacao_2025 not between 0 and 100
        or meta_alfabetizacao_2026 not between 0 and 100
        or meta_alfabetizacao_2027 not between 0 and 100
        or meta_alfabetizacao_2028 not between 0 and 100
        or meta_alfabetizacao_2029 not between 0 and 100
        or meta_alfabetizacao_2030 not between 0 and 100
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
),

proportion_rows as (
    select
        proporcao_aluno_nivel_0 is null
        or proporcao_aluno_nivel_1 is null
        or proporcao_aluno_nivel_2 is null
        or proporcao_aluno_nivel_3 is null
        or proporcao_aluno_nivel_4 is null
        or proporcao_aluno_nivel_5 is null
        or proporcao_aluno_nivel_6 is null
        or proporcao_aluno_nivel_7 is null
        or proporcao_aluno_nivel_8 is null
        or abs(
            proporcao_aluno_nivel_0 + proporcao_aluno_nivel_1
            + proporcao_aluno_nivel_2 + proporcao_aluno_nivel_3
            + proporcao_aluno_nivel_4 + proporcao_aluno_nivel_5
            + proporcao_aluno_nivel_6 + proporcao_aluno_nivel_7
            + proporcao_aluno_nivel_8 - 100
        ) > 0.5 as invalid
    from {{ ref('silver_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        proporcao_aluno_nivel_0 is null
        or proporcao_aluno_nivel_1 is null
        or proporcao_aluno_nivel_2 is null
        or proporcao_aluno_nivel_3 is null
        or proporcao_aluno_nivel_4 is null
        or proporcao_aluno_nivel_5 is null
        or proporcao_aluno_nivel_6 is null
        or proporcao_aluno_nivel_7 is null
        or proporcao_aluno_nivel_8 is null
        or abs(
            proporcao_aluno_nivel_0 + proporcao_aluno_nivel_1
            + proporcao_aluno_nivel_2 + proporcao_aluno_nivel_3
            + proporcao_aluno_nivel_4 + proporcao_aluno_nivel_5
            + proporcao_aluno_nivel_6 + proporcao_aluno_nivel_7
            + proporcao_aluno_nivel_8 - 100
        ) > 0.5
    from {{ ref('silver_uf') }}
    where release_id = '{{ var("release_id") }}'
),

rule_metrics as (
    select
        'percentage_ranges' as rule_id,
        countif(invalid) as metric_value,
        if(countif(invalid) = 0, 'pass', 'critical') as severity,
        if(countif(invalid) = 0, 'promote', 'quarantine_and_block') as action,
        'required_rates_proportions_participation_annual_targets_optional' as details
    from range_rows
    union all
    select
        'proportions_sum' as rule_id,
        countif(invalid) as metric_value,
        if(countif(invalid) = 0, 'pass', 'critical') as severity,
        if(countif(invalid) = 0, 'promote', 'quarantine_and_block') as action,
        'municipio_and_uf_sum_99_5_to_100_5' as details
    from proportion_rows
)

select
    '{{ var("release_id") }}' as release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
from rule_metrics
