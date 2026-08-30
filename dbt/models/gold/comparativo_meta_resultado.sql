{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    unique_key=['release_id', 'ano_resultado', 'nivel_geografico', 'id_geografia', 'rede'],
    partition_by={'field': 'ano_particao', 'data_type': 'date', 'granularity': 'year'},
    cluster_by=['release_id', 'nivel_geografico', 'id_geografia', 'rede']
) }}

with metas_base as (
    select
        release_id,
        ano as ano_referencia,
        'municipio' as nivel_geografico,
        id_municipio as id_geografia,
        rede,
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        ano as ano_referencia,
        'uf' as nivel_geografico,
        sigla_uf as id_geografia,
        rede,
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        ano as ano_referencia,
        'brasil' as nivel_geografico,
        'BRASIL' as id_geografia,
        rede,
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
),

metas_longas as (
    select
        release_id,
        ano_referencia,
        nivel_geografico,
        id_geografia,
        rede,
        cast(right(nome_meta, 4) as int64) as ano_meta,
        meta_alfabetizacao
    from metas_base
    unpivot include nulls (meta_alfabetizacao for nome_meta in (
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    ))
),

metas_escolhidas as (
    select *
    from metas_longas
    where ano_referencia <= ano_meta and meta_alfabetizacao is not null
    qualify row_number() over (
        partition by release_id, ano_meta, nivel_geografico, id_geografia, rede
        order by ano_referencia desc
    ) = 1
),

resultados as (
    select
        release_id,
        ano as ano_resultado,
        ano_particao,
        'municipio' as nivel_geografico,
        id_municipio as id_geografia,
        nome_municipio as nome_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('indicador_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        ano as ano_resultado,
        ano_particao,
        'uf' as nivel_geografico,
        sigla_uf as id_geografia,
        sigla_uf as nome_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        ano as ano_resultado,
        ano_particao,
        'brasil' as nivel_geografico,
        'BRASIL' as id_geografia,
        'Brasil' as nome_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
)

select
    resultado.release_id,
    resultado.ano_resultado,
    resultado.ano_particao,
    resultado.nivel_geografico,
    resultado.id_geografia,
    resultado.nome_geografia,
    resultado.rede,
    meta.ano_referencia,
    meta.meta_alfabetizacao,
    resultado.taxa_resultado,
    resultado.taxa_resultado - meta.meta_alfabetizacao as gap_pp,
    if(
        resultado.taxa_resultado >= meta.meta_alfabetizacao,
        'atingida',
        'nao_atingida'
    ) as status_meta
from resultados as resultado
inner join metas_escolhidas as meta
    on
        resultado.release_id = meta.release_id
        and resultado.ano_resultado = meta.ano_meta
        and resultado.nivel_geografico = meta.nivel_geografico
        and resultado.id_geografia = meta.id_geografia
        and resultado.rede = meta.rede
