{{ config(
  materialized='incremental',
  full_refresh=false,
  incremental_strategy='merge',
  unique_key=['release_id', 'ano', 'id_municipio', 'rede'],
  partition_by={'field': 'ano_particao', 'data_type': 'date', 'granularity': 'year'},
  cluster_by=['release_id', 'id_municipio', 'rede']
) }}

with recursive candidate_registry as (
    select
        release_id,
        reference_year,
        baseline_release_id,
        0 as chain_level
    from {{ source('ops', 'release_registry') }}
    where release_id = '{{ var("release_id") }}' and status = 'succeeded'
),

release_chain as (
    select
        release_id,
        reference_year,
        baseline_release_id,
        chain_level
    from candidate_registry
    union all
    select
        registry.release_id,
        registry.reference_year,
        registry.baseline_release_id,
        ancestor.chain_level + 1 as chain_level
    from release_chain as ancestor
    inner join {{ source('ops', 'release_registry') }} as registry
        on ancestor.baseline_release_id = registry.release_id
    where registry.release_id != '__bootstrap__'
),

selected_releases as (
    select
        release_id,
        reference_year
    from release_chain
    qualify row_number() over (
        partition by reference_year order by chain_level
    ) = 1
),

history as (
    select indicador.*
    from {{ ref('indicador_municipio') }} as indicador
    inner join selected_releases as selected on indicador.release_id = selected.release_id
),

evolucao as (
    select
        *,
        lag(taxa_alfabetizacao) over (
            partition by id_municipio, rede order by ano
        ) as taxa_ano_anterior
    from history
)

select
    *,
    taxa_alfabetizacao - taxa_ano_anterior as variacao_pp
from evolucao
where release_id = '{{ var("release_id") }}'
