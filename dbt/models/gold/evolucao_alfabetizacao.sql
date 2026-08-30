{{ config(
  materialized='incremental',
  incremental_strategy='insert_overwrite',
  unique_key=['release_id', 'ano', 'id_municipio', 'rede'],
  partition_by={'field': 'ano_particao', 'data_type': 'date', 'granularity': 'year'},
  cluster_by=['release_id', 'id_municipio', 'rede']
) }}

with evolucao as (
    select
        *,
        lag(taxa_alfabetizacao) over (
            partition by release_id, id_municipio, rede order by ano
        ) as taxa_ano_anterior
    from {{ ref('indicador_municipio') }}
    where release_id = '{{ var("release_id") }}'
)

select
    *,
    taxa_alfabetizacao - taxa_ano_anterior as variacao_pp
from evolucao
