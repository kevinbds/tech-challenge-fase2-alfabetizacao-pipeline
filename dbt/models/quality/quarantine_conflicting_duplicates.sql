{{ config(
    incremental_strategy='merge',
    pre_hook="{{ replace_candidate_rows() }}",
    unique_key=['release_id', 'table_name', 'business_key_hash', 'row_hash']
) }}

with conflicts as (
    select
        *,
        count(distinct row_hash) over (
            partition by release_id, table_name, business_key_hash
        ) as variants
    from {{ ref('duplicate_candidates') }}
)

select
    release_id,
    table_name,
    business_key_hash,
    row_hash,
    'critical' as severity,
    'quarantine_and_block' as action,
    max(source_run_id) as source_run_id,
    max(ingested_at) as detected_at
from conflicts
where variants > 1
group by release_id, table_name, business_key_hash, row_hash
