{{ config(materialized='table', schema='quality', alias='release_volume_metric') }}

with candidate_registry as (
    select baseline_release_id
    from {{ source('ops', 'release_registry') }}
    where release_id = '{{ var("release_id") }}' and status = 'succeeded'
),

target_release_count as (
    select count(*) as row_count
    from {{ ref('silver_municipio') }}
    where release_id = '{{ var("release_id") }}'
),

baseline_release_count as (
    select count(*) as row_count
    from {{ ref('silver_municipio') }} as baseline
    cross join candidate_registry as registry
    where baseline.release_id = registry.baseline_release_id
)

select
    baseline_counts.row_count as baseline_count,
    candidate_counts.row_count as target_count,
    100.0 * (candidate_counts.row_count - baseline_counts.row_count)
    / nullif(baseline_counts.row_count, 0) as volume_delta
from target_release_count as candidate_counts
cross join baseline_release_count as baseline_counts
