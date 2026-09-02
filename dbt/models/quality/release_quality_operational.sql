{{ config(materialized='table', schema='quality', alias='release_quality_operational') }}

with repeated_keys as (
    select count(*) as copies from {{ ref('stg_alunos') }}
    where release_id = '{{ var("release_id") }}'
    group by ano, id_municipio, id_escola, id_aluno
),

repeated_metric as (
    select 100.0 * coalesce(sum(copies - 1), 0) / nullif(sum(copies), 0) as metric_value
    from repeated_keys
),

freshness as (
    select max({{ days_since('verified_at') }}) as days_since_success
    from {{ source('ops', 'release_files') }}
    where release_id = '{{ var("release_id") }}' and status = 'selected'
),

rules as (
    select
        'repeated_evaluation_or_target_rate' as rule_id,
        coalesce(metric_value, 0) as metric_value,
        case
            when coalesce(metric_value, 0) <= 0.01 then 'pass'
            when metric_value <= 0.50 then 'warning' else 'critical'
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
        abs(volume_delta) as metric_value,
        case
            when baseline_count = 0 then 'warning'
            when target_count = 0 or volume_delta < -50 then 'critical'
            when abs(volume_delta) > 20 then 'warning' else 'pass'
        end as severity,
        case
            when target_count = 0 or volume_delta < -50 then 'block_promotion'
            when baseline_count = 0 or abs(volume_delta) > 20 then 'continue_with_alert'
            else 'promote'
        end as action,
        if(baseline_count = 0, 'baseline_missing', 'silver_municipio_release_total') as details
    from {{ ref('release_volume_metric') }}
    union all
    select
        'pipeline_freshness' as rule_id,
        days_since_success as metric_value,
        if(days_since_success <= 35, 'pass', 'critical') as severity,
        if(days_since_success <= 35, 'promote', 'block_promotion') as action,
        'oldest_selected_source_verification_days' as details
    from freshness
    union all
    select
        'identical_duplicate' as rule_id,
        coalesce(sum(copies - 1), 0) as metric_value,
        if(coalesce(sum(copies - 1), 0) = 0, 'pass', 'warning') as severity,
        if(coalesce(sum(copies - 1), 0) = 0, 'promote', 'deduplicate_and_alert') as action,
        'audit_identical_duplicates_excess_copies' as details
    from {{ ref('audit_identical_duplicates') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'conflicting_duplicate' as rule_id,
        count(distinct business_key_hash) as metric_value,
        if(count(distinct business_key_hash) = 0, 'pass', 'critical') as severity,
        if(count(distinct business_key_hash) = 0, 'promote', 'quarantine_and_block') as action,
        'quarantine_conflicting_business_keys' as details
    from {{ ref('quarantine_conflicting_duplicates') }}
    where release_id = '{{ var("release_id") }}'
)

select
    '{{ var("release_id") }}' as release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
from rules
