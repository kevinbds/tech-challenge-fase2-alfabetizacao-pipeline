{{ config(materialized='table', schema='quality', alias='release_quality_core') }}

with meta_uf_rejections as (
    select
        countif(
            coalesce(
                ano = 2024 and sigla_uf = 'RR' and rede = 'publica'
                and reason_code
                = 'taxa_alfabetizacao_and_percentual_participacao_missing', false
            )
        ) as expected_rows,
        countif(
            not coalesce(
                ano = 2024 and sigla_uf = 'RR' and rede = 'publica'
                and reason_code
                = 'taxa_alfabetizacao_and_percentual_participacao_missing', false
            )
        ) as unexpected_rows
    from {{ ref('quarantine_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
),

rules as (
    select
        'required_keys' as rule_id,
        greatest(
            coalesce(keys.null_rate, 0),
            6 - keys.covered_sources + keys.empty_sources + keys.unexpected_sources
            + 6 - keys.covered_silver_tables,
            meta_uf_rejections.unexpected_rows,
            meta_uf_rejections.expected_rows - 1
        ) as metric_value,
        case
            when
                coalesce(keys.null_rate, 0) != 0 or keys.covered_sources != 6
                or keys.empty_sources != 0 or keys.unexpected_sources != 0
                or keys.covered_silver_tables != 6
                or meta_uf_rejections.unexpected_rows != 0
                or meta_uf_rejections.expected_rows > 1 then 'critical'
            when meta_uf_rejections.expected_rows = 1 then 'warning'
            else 'pass'
        end as severity,
        case
            when
                coalesce(keys.null_rate, 0) != 0 or keys.covered_sources != 6
                or keys.empty_sources != 0 or keys.unexpected_sources != 0
                or keys.covered_silver_tables != 6
                or meta_uf_rejections.unexpected_rows != 0
                or meta_uf_rejections.expected_rows > 1 then 'quarantine_and_block'
            when meta_uf_rejections.expected_rows = 1 then 'continue_with_alert'
            else 'promote'
        end as action,
        case
            when
                meta_uf_rejections.expected_rows = 1
                and meta_uf_rejections.unexpected_rows = 0
                then
                    'six_non_empty_sources_and_silver_required_keys_with_rr_2024_publica_exception'
            else 'six_non_empty_sources_and_silver_required_keys'
        end as details
    from {{ ref('release_quality_key_coverage') }} as keys
    cross join meta_uf_rejections
    union all
    select
        'uniqueness_after_quarantine' as rule_id,
        coalesce(keys.duplicate_rate, 0) as metric_value,
        if(coalesce(keys.duplicate_rate, 0) = 0, 'pass', 'critical') as severity,
        if(
            coalesce(keys.duplicate_rate, 0) = 0,
            'promote', 'quarantine_and_block'
        ) as action,
        'six_silver_business_keys' as details
    from {{ ref('release_quality_key_coverage') }} as keys
    union all
    select
        'relationships' as rule_id,
        least(
            coalesce(
                100.0 * (measures.checked_rows - measures.missing_rows)
                / nullif(measures.checked_rows, 0),
                0
            ),
            if(
                measures.actual_relationship_count
                = measures.expected_relationship_count
                and measures.distinct_relationship_count
                = measures.expected_relationship_count
                and measures.missing_expected_relationship_count = 0
                and measures.unexpected_relationship_count = 0,
                100.0 * (
                    measures.expected_relationship_count
                    - measures.empty_relationship_count
                ) / nullif(measures.expected_relationship_count, 0),
                0
            )
        ) as metric_value,
        if(
            measures.expected_relationship_count = 7
            and measures.actual_relationship_count = 7
            and measures.distinct_relationship_count = 7
            and measures.missing_expected_relationship_count = 0
            and measures.empty_relationship_count = 0
            and measures.unexpected_relationship_count = 0
            and measures.missing_rows = 0,
            'pass', 'critical'
        ) as severity,
        if(
            measures.expected_relationship_count = 7
            and measures.actual_relationship_count = 7
            and measures.distinct_relationship_count = 7
            and measures.missing_expected_relationship_count = 0
            and measures.empty_relationship_count = 0
            and measures.unexpected_relationship_count = 0
            and measures.missing_rows = 0,
            'promote', 'quarantine_and_block'
        ) as action,
        'sete_relacoes_de_referencia' as details
    from {{ ref('release_quality_measurements') }} as measures
    union all
    select
        'gold_core_nulls' as rule_id,
        100.0 * measures.gold_null_count / nullif(measures.gold_row_count, 0)
            as metric_value,
        if(
            measures.gold_row_count > 0 and measures.gold_null_count = 0,
            'pass', 'critical'
        ) as severity,
        if(
            measures.gold_row_count > 0 and measures.gold_null_count = 0,
            'promote', 'block_promotion'
        ) as action,
        'non_empty_gold_core_and_directory_columns' as details
    from {{ ref('release_quality_measurements') }} as measures
    union all
    select
        'optional_null_delta' as rule_id,
        measures.optional_null_delta as metric_value,
        if(
            measures.baseline_rows = 0 or measures.optional_null_delta > 5,
            'warning', 'pass'
        ) as severity,
        if(
            measures.baseline_rows = 0 or measures.optional_null_delta > 5,
            'continue_with_alert', 'promote'
        ) as action,
        if(
            measures.baseline_rows = 0,
            'baseline_missing', 'media_portugues_pp_delta'
        ) as details
    from {{ ref('release_quality_measurements') }} as measures
    union all
    select
        rule_id,
        metric_value,
        severity,
        action,
        details
    from {{ ref('release_percentage_metrics') }}
    where rule_id = 'percentage_ranges'
    union all
    select
        'non_negative_measurements' as rule_id,
        measures.invalid_measurements as metric_value,
        if(measures.invalid_measurements = 0, 'pass', 'critical') as severity,
        if(
            measures.invalid_measurements = 0,
            'promote', 'quarantine_and_block'
        ) as action,
        'silver_measurements' as details
    from {{ ref('release_quality_measurements') }} as measures
    union all
    select
        rule_id,
        metric_value,
        severity,
        action,
        details
    from {{ ref('release_percentage_metrics') }}
    where rule_id = 'proportions_sum'
)

select
    '{{ var("release_id") }}' as release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
from rules
