{{ config(
    materialized='incremental',
    full_refresh=false,
    incremental_strategy='merge',
    unique_key=['release_id', 'ano_meta', 'nivel_geografico', 'id_geografia', 'rede'],
    partition_by={'field': 'ano_particao', 'data_type': 'date', 'granularity': 'year'},
    cluster_by=['release_id', 'nivel_geografico', 'id_geografia', 'rede']
) }}

with metas_base as (
    select
        meta.release_id,
        meta.ano as ano_referencia,
        'municipio' as nivel_geografico,
        meta.id_municipio as id_geografia,
        directory.nome as nome_geografia,
        meta.rede,
        meta.meta_alfabetizacao_2024,
        meta.meta_alfabetizacao_2025,
        meta.meta_alfabetizacao_2026,
        meta.meta_alfabetizacao_2027,
        meta.meta_alfabetizacao_2028,
        meta.meta_alfabetizacao_2029,
        meta.meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_municipio') }} as meta
    inner join {{ source('diretorios', 'municipio') }} as directory
        on meta.id_municipio = directory.id_municipio
    where meta.release_id = '{{ var("release_id") }}' and meta.rede = 'municipal'
    union all
    select
        release_id,
        ano as ano_referencia,
        'uf' as nivel_geografico,
        sigla_uf as id_geografia,
        sigla_uf as nome_geografia,
        rede,
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}' and rede = 'publica'
    union all
    select
        release_id,
        ano as ano_referencia,
        'brasil' as nivel_geografico,
        'BRASIL' as id_geografia,
        'Brasil' as nome_geografia,
        rede,
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}' and rede = 'publica'
),

metas_longas as (
    select
        release_id,
        ano_referencia,
        nivel_geografico,
        id_geografia,
        nome_geografia,
        rede,
        cast(right(nome_meta, 4) as int64) as ano_meta,
        meta_alfabetizacao
    from metas_base
    unpivot (meta_alfabetizacao for nome_meta in (
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
    select
        release_id,
        ano_referencia,
        ano_meta,
        nivel_geografico,
        id_geografia,
        nome_geografia,
        rede,
        meta_alfabetizacao
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
        'municipio' as nivel_geografico,
        id_municipio as id_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('indicador_municipio') }}
    where release_id = '{{ var("release_id") }}' and rede = 'municipal'
    union all
    select
        release_id,
        ano as ano_resultado,
        'uf' as nivel_geografico,
        sigla_uf as id_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('silver_uf') }}
    where release_id = '{{ var("release_id") }}' and rede = 'publica'
    union all
    select
        release_id,
        ano as ano_resultado,
        'brasil' as nivel_geografico,
        'BRASIL' as id_geografia,
        rede,
        taxa_alfabetizacao as taxa_resultado
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}' and rede = 'publica'
)

select
    meta.release_id,
    meta.ano_meta,
    resultado.ano_resultado,
    cast(cast(meta.ano_meta as string) || '-01-01' as date) as ano_particao,
    meta.nivel_geografico,
    meta.id_geografia,
    meta.nome_geografia,
    meta.rede,
    meta.ano_referencia,
    meta.meta_alfabetizacao,
    resultado.taxa_resultado,
    case
        when resultado.taxa_resultado is not null
            then resultado.taxa_resultado - meta.meta_alfabetizacao
    end as gap_pp,
    case
        when resultado.taxa_resultado is null then null
        when resultado.taxa_resultado >= meta.meta_alfabetizacao then 'atingida'
        else 'nao_atingida'
    end as status_meta
from metas_escolhidas as meta
left join resultados as resultado
    on
        meta.release_id = resultado.release_id
        and meta.ano_meta = resultado.ano_resultado
        and meta.nivel_geografico = resultado.nivel_geografico
        and meta.id_geografia = resultado.id_geografia
        and meta.rede = resultado.rede
