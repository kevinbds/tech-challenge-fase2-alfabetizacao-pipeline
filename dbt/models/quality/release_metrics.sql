{{ config(materialized='table', schema='quality', alias='release_metrics') }}

select * from {{ ref('release_quality_core') }}
union all
select * from {{ ref('release_quality_operational') }}
