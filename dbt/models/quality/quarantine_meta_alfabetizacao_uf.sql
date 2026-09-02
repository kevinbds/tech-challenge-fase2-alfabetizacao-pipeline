{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    pre_hook="{{ replace_candidate_rows() }}",
    schema='quarantine',
    alias='meta_alfabetizacao_uf_rejections',
    unique_key=['release_id', 'ano', 'sigla_uf', 'rede', 'source_run_id']
) }}

select
    release_id,
    ano,
    sigla_uf,
    rede,
    source_run_id,
    ingested_at,
    'meta_alfabetizacao_uf' as source_table,
    case
        when taxa_alfabetizacao is null and percentual_participacao is null
            then 'taxa_alfabetizacao_and_percentual_participacao_missing'
        when taxa_alfabetizacao is null then 'taxa_alfabetizacao_missing'
        else 'percentual_participacao_missing'
    end as reason_code
from {{ ref('stg_meta_alfabetizacao_uf') }}
where
    release_id = '{{ var("release_id") }}'
    and (taxa_alfabetizacao is null or percentual_participacao is null)
