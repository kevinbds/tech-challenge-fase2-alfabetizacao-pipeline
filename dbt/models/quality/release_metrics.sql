{{ config(materialized='table', schema='quality', alias='release_metrics') }}

with silver_keys as (
    select
        'municipio' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        cast(null as string) as extra_id
    from `{{ var("project_id") }}.silver.silver_municipio`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'uf' as table_name,
        ano,
        sigla_uf as geography_id,
        rede,
        cast(null as string) as extra_id
    from `{{ var("project_id") }}.silver.silver_uf`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_municipio' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        cast(null as string) as extra_id
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_municipio`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_uf' as table_name,
        ano,
        sigla_uf as geography_id,
        rede,
        cast(null as string) as extra_id
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_uf`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_brasil' as table_name,
        ano,
        'BRASIL' as geography_id,
        rede,
        cast(null as string) as extra_id
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_brasil`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'alunos' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        id_escola || '|' || id_aluno as extra_id
    from `{{ var("project_id") }}.silver_restricted.silver_alunos`
    where release_id = '{{ var("release_id") }}'
),

key_counts as (
    select
        count(*) as row_count,
        countif(
            ano is null or geography_id is null or rede is null
            or (table_name = 'alunos' and extra_id is null)
        ) as null_keys
    from silver_keys
),

duplicate_keys as (
    select count(*) as copies
    from silver_keys
    group by table_name, ano, geography_id, rede, extra_id
),

key_metrics as (
    select
        max(100.0 * key_counts.null_keys / nullif(key_counts.row_count, 0)) as null_rate,
        100.0 * coalesce(sum(duplicate_keys.copies - 1), 0)
        / nullif(max(key_counts.row_count), 0)
            as duplicate_rate
    from key_counts
    cross join duplicate_keys
),

relationships as (
    select
        count(*) as student_count,
        countif(m.id_municipio is null) as orphan_count
    from `{{ var("project_id") }}.silver_restricted.silver_alunos` as a
    left join `{{ var("project_id") }}.silver.silver_municipio` as m
        on
            a.release_id = m.release_id
            and a.ano = m.ano
            and a.id_municipio = m.id_municipio
            and a.rede = m.rede
    where a.release_id = '{{ var("release_id") }}'
),

gold_core_rows as (
    select
        ano is null or id_municipio is null or rede is null
        or taxa_alfabetizacao is null or nome_municipio is null
        or sigla_uf is null as invalid
    from `{{ var("project_id") }}.gold.indicador_municipio`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        ano_resultado is null or nivel_geografico is null
        or id_geografia is null or rede is null or taxa_resultado is null
        or meta_alfabetizacao is null
    from `{{ var("project_id") }}.gold.comparativo_meta_resultado`
    where release_id = '{{ var("release_id") }}'
),

gold_core as (
    select
        count(*) as row_count,
        countif(invalid) as null_count
    from gold_core_rows
),

optional_rates as (
    select
        countif(m.release_id = '{{ var("release_id") }}') as target_rows,
        countif(m.release_id = '{{ var("release_id") }}' and m.media_portugues is null)
            as target_nulls,
        countif(m.release_id = active.release_id) as baseline_rows,
        countif(m.release_id = active.release_id and m.media_portugues is null)
            as baseline_nulls
    from `{{ var("project_id") }}.silver.silver_municipio` as m
    cross join `{{ var("project_id") }}.ops.active_release` as active
    where active.singleton_key = true
),

optional_delta as (
    select
        baseline_rows,
        100.0 * target_nulls / nullif(target_rows, 0)
        - 100.0 * baseline_nulls / nullif(baseline_rows, 0) as metric_value
    from optional_rates
),

percentage_metrics as (
    select * from {{ ref('release_percentage_metrics') }}
    where release_id = '{{ var("release_id") }}'
),

measurement_violations as (
    select
        countif(
            media_portugues < 0 or taxa_alfabetizacao < 0
            or proporcao_aluno_nivel_0 < 0 or proporcao_aluno_nivel_1 < 0
            or proporcao_aluno_nivel_2 < 0 or proporcao_aluno_nivel_3 < 0
            or proporcao_aluno_nivel_4 < 0 or proporcao_aluno_nivel_5 < 0
            or proporcao_aluno_nivel_6 < 0 or proporcao_aluno_nivel_7 < 0
            or proporcao_aluno_nivel_8 < 0
        ) as invalid_count
    from `{{ var("project_id") }}.silver.silver_municipio`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            media_portugues < 0 or taxa_alfabetizacao < 0
            or proporcao_aluno_nivel_0 < 0 or proporcao_aluno_nivel_1 < 0
            or proporcao_aluno_nivel_2 < 0 or proporcao_aluno_nivel_3 < 0
            or proporcao_aluno_nivel_4 < 0 or proporcao_aluno_nivel_5 < 0
            or proporcao_aluno_nivel_6 < 0 or proporcao_aluno_nivel_7 < 0
            or proporcao_aluno_nivel_8 < 0
        ) as invalid_count
    from `{{ var("project_id") }}.silver.silver_uf`
    where release_id = '{{ var("release_id") }}'
    union all
    select countif(proficiencia < 0 or peso_aluno < 0) as invalid_count
    from `{{ var("project_id") }}.silver_restricted.silver_alunos`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            or meta_alfabetizacao_2024 < 0 or meta_alfabetizacao_2025 < 0
            or meta_alfabetizacao_2026 < 0 or meta_alfabetizacao_2027 < 0
            or meta_alfabetizacao_2028 < 0 or meta_alfabetizacao_2029 < 0
            or meta_alfabetizacao_2030 < 0
        ) as invalid_count
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_municipio`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            or meta_alfabetizacao_2024 < 0 or meta_alfabetizacao_2025 < 0
            or meta_alfabetizacao_2026 < 0 or meta_alfabetizacao_2027 < 0
            or meta_alfabetizacao_2028 < 0 or meta_alfabetizacao_2029 < 0
            or meta_alfabetizacao_2030 < 0
        ) as invalid_count
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_uf`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        countif(
            taxa_alfabetizacao < 0 or percentual_participacao < 0
            or meta_alfabetizacao_2024 < 0 or meta_alfabetizacao_2025 < 0
            or meta_alfabetizacao_2026 < 0 or meta_alfabetizacao_2027 < 0
            or meta_alfabetizacao_2028 < 0 or meta_alfabetizacao_2029 < 0
            or meta_alfabetizacao_2030 < 0
        ) as invalid_count
    from `{{ var("project_id") }}.silver.silver_meta_alfabetizacao_brasil`
    where release_id = '{{ var("release_id") }}'
),

repeated_keys as (
    select count(*) as copies
    from `{{ var("project_id") }}.staging.stg_alunos`
    where release_id = '{{ var("release_id") }}'
    group by ano, id_municipio, id_escola, id_aluno
),

repeated_metric as (
    select
        100.0 * coalesce(sum(copies - 1), 0) / nullif(sum(copies), 0)
            as metric_value
    from repeated_keys
),

active_pointer as (
    select active.release_id
    from `{{ var("project_id") }}.ops.active_release` as active
    where active.singleton_key = true
),

target_partition_counts as (
    select
        ano,
        count(*) as row_count
    from `{{ var("project_id") }}.silver.silver_municipio`
    where release_id = '{{ var("release_id") }}'
    group by ano
),

baseline_partition_counts as (
    select
        baseline.ano,
        count(*) as row_count
    from `{{ var("project_id") }}.silver.silver_municipio` as baseline
    cross join active_pointer
    where baseline.release_id = active_pointer.release_id
    group by baseline.ano
),

partition_counts as (
    select
        rows_target.ano,
        rows_target.row_count as target_count,
        rows_baseline.row_count as baseline_count
    from target_partition_counts as rows_target
    full outer join baseline_partition_counts as rows_baseline
        on rows_target.ano = rows_baseline.ano
),

volume_metric as (
    select
        countif(baseline_count is not null) as baseline_partitions,
        countif(target_count is null or target_count = 0) as zero_partitions,
        min(
            100.0 * (coalesce(target_count, 0) - baseline_count)
            / nullif(baseline_count, 0)
        ) as minimum_delta,
        max(
            abs(
                100.0 * (coalesce(target_count, 0) - baseline_count)
                / nullif(baseline_count, 0)
            )
        ) as maximum_delta
    from partition_counts
),

freshness as (
    select date_diff(current_date(), date(completed_at), day) as days_since_success
    from `{{ var("project_id") }}.ops.release_registry`
    where release_id = '{{ var("release_id") }}' and status = 'succeeded'
),

rule_metrics as (
    select
        'required_keys' as rule_id,
        coalesce(null_rate, 0) as metric_value,
        if(coalesce(null_rate, 0) = 0, 'pass', 'critical') as severity,
        if(coalesce(null_rate, 0) = 0, 'promote', 'quarantine_and_block') as action,
        'six_silver_required_keys' as details
    from key_metrics
    union all
    select
        'uniqueness_after_quarantine' as rule_id,
        coalesce(duplicate_rate, 0) as metric_value,
        if(coalesce(duplicate_rate, 0) = 0, 'pass', 'critical') as severity,
        if(coalesce(duplicate_rate, 0) = 0, 'promote', 'quarantine_and_block') as action,
        'six_silver_business_keys' as details
    from key_metrics
    union all
    select
        'relationships' as rule_id,
        100.0 * orphan_count / nullif(student_count, 0) as metric_value,
        if(orphan_count = 0, 'pass', 'critical') as severity,
        if(orphan_count = 0, 'promote', 'quarantine_and_block') as action,
        'alunos_to_municipio_by_release_ano_rede' as details
    from relationships
    union all
    select
        'gold_core_nulls' as rule_id,
        100.0 * null_count / nullif(row_count, 0) as metric_value,
        if(null_count = 0, 'pass', 'critical') as severity,
        if(null_count = 0, 'promote', 'block_promotion') as action,
        'indicador_municipio_core_and_directory_columns' as details
    from gold_core
    union all
    select
        'optional_null_delta' as rule_id,
        metric_value,
        if(baseline_rows = 0 or metric_value > 5, 'warning', 'pass') as severity,
        if(baseline_rows = 0 or metric_value > 5, 'continue_with_alert', 'promote') as action,
        if(baseline_rows = 0, 'baseline_missing', 'media_portugues_pp_delta') as details
    from optional_delta
    union all
    select
        rule_id,
        metric_value,
        severity,
        action,
        details
    from percentage_metrics
    where rule_id = 'percentage_ranges'
    union all
    select
        'non_negative_measurements' as rule_id,
        sum(invalid_count) as metric_value,
        if(sum(invalid_count) = 0, 'pass', 'critical') as severity,
        if(sum(invalid_count) = 0, 'promote', 'quarantine_and_block') as action,
        'silver_measurements' as details
    from measurement_violations
    union all
    select
        rule_id,
        metric_value,
        severity,
        action,
        details
    from percentage_metrics
    where rule_id = 'proportions_sum'
    union all
    select
        'repeated_evaluation_or_target_rate' as rule_id,
        coalesce(metric_value, 0) as metric_value,
        case
            when coalesce(metric_value, 0) <= 0.01 then 'pass'
            when metric_value <= 0.50 then 'warning'
            else 'critical'
        end as severity,
        case
            when coalesce(metric_value, 0) <= 0.01 then 'promote'
            when metric_value <= 0.50 then 'continue_with_alert'
            else 'quarantine_and_block'
        end as action,
        'stg_alunos_pre_deduplication' as details
    from repeated_metric
    union all
    select
        'partition_volume' as rule_id,
        maximum_delta,
        case
            when baseline_partitions = 0 then 'warning'
            when zero_partitions > 0 or minimum_delta < -50 then 'critical'
            when maximum_delta > 20 then 'warning'
            else 'pass'
        end as severity,
        case
            when zero_partitions > 0 or minimum_delta < -50 then 'block_promotion'
            when baseline_partitions = 0 or maximum_delta > 20 then 'continue_with_alert'
            else 'promote'
        end as action,
        if(baseline_partitions = 0, 'baseline_missing', 'silver_municipio_by_ano') as details
    from volume_metric
    union all
    select
        'pipeline_freshness' as rule_id,
        days_since_success,
        if(days_since_success <= 35, 'pass', 'critical') as severity,
        if(days_since_success <= 35, 'promote', 'block_promotion') as action,
        'release_registry_completed_at_days' as details
    from freshness
    union all
    select
        'identical_duplicate' as rule_id,
        coalesce(sum(copies - 1), 0) as metric_value,
        if(coalesce(sum(copies - 1), 0) = 0, 'pass', 'warning') as severity,
        if(coalesce(sum(copies - 1), 0) = 0, 'promote', 'deduplicate_and_alert') as action,
        'audit_identical_duplicates_excess_copies' as details
    from `{{ var("project_id") }}.quality.audit_identical_duplicates`
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'conflicting_duplicate' as rule_id,
        count(distinct business_key_hash) as metric_value,
        if(count(distinct business_key_hash) = 0, 'pass', 'critical') as severity,
        if(count(distinct business_key_hash) = 0, 'promote', 'quarantine_and_block') as action,
        'quarantine_conflicting_business_keys' as details
    from `{{ var("project_id") }}.quality.quarantine_conflicting_duplicates`
    where release_id = '{{ var("release_id") }}'
)

select
    '{{ var("release_id") }}' as release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
from rule_metrics
