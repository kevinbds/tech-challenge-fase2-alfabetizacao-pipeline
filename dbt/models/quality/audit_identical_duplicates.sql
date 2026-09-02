{{ config(
    incremental_strategy='merge',
    pre_hook="{{ replace_candidate_rows() }}",
    unique_key=['release_id', 'table_name', 'business_key_hash', 'source_run_id']
) }}

with duplicates as (
    select
        *,
        count(*) over (partition by release_id, table_name, business_key_hash) as copies,
        count(distinct row_hash) over (
            partition by release_id, table_name, business_key_hash
        ) as variants
    from {{ ref('duplicate_candidates') }}
)

select
    release_id,
    table_name,
    business_key_hash,
    source_run_id,
    max(ingested_at) as detected_at,
    max(copies) as copies
from duplicates
where copies > 1 and variants = 1
group by release_id, table_name, business_key_hash, source_run_id
