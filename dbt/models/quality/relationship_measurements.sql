{{ config(materialized='table', schema='quality', alias='relationship_measurements') }}

with metas_uf_base as (
    select
        release_id,
        ano as ano_referencia,
        sigla_uf,
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
),

metas_uf_escolhidas as (
    select
        release_id,
        sigla_uf,
        rede,
        cast(right(nome_meta, 4) as int64) as ano_resultado
    from metas_uf_base
    unpivot include nulls (meta_alfabetizacao for nome_meta in (
        meta_alfabetizacao_2024,
        meta_alfabetizacao_2025,
        meta_alfabetizacao_2026,
        meta_alfabetizacao_2027,
        meta_alfabetizacao_2028,
        meta_alfabetizacao_2029,
        meta_alfabetizacao_2030
    ))
    where
        ano_referencia <= cast(right(nome_meta, 4) as int64)
        and meta_alfabetizacao is not null
    qualify row_number() over (
        partition by release_id, sigla_uf, rede, nome_meta
        order by ano_referencia desc
    ) = 1
),

directory_ufs as (
    select distinct sigla_uf
    from {{ source('diretorios', 'municipio') }}
    where sigla_uf is not null
),

checks as (
    select
        'alunos_diretorio_municipio' as relation_name,
        count(*) as checked_rows,
        countif(d.id_municipio is null) as missing_rows
    from {{ ref('silver_alunos') }} as a
    left join {{ source('diretorios', 'municipio') }} as d
        on a.id_municipio = d.id_municipio
    where a.release_id = '{{ var("release_id") }}'
    union all
    select
        'municipio_diretorio' as relation_name,
        count(*) as checked_rows,
        countif(d.id_municipio is null) as missing_rows
    from {{ ref('silver_municipio') }} as m
    left join {{ source('diretorios', 'municipio') }} as d
        on m.id_municipio = d.id_municipio
    where m.release_id = '{{ var("release_id") }}'
    union all
    select
        'uf_diretorio' as relation_name,
        count(*) as checked_rows,
        countif(d.sigla_uf is null) as missing_rows
    from {{ ref('silver_uf') }} as u
    left join directory_ufs as d on u.sigla_uf = d.sigla_uf
    where u.release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_municipio_diretorio' as relation_name,
        count(*) as checked_rows,
        countif(d.id_municipio is null) as missing_rows
    from {{ ref('silver_meta_alfabetizacao_municipio') }} as meta
    left join {{ source('diretorios', 'municipio') }} as d
        on meta.id_municipio = d.id_municipio
    where meta.release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_uf_diretorio' as relation_name,
        count(*) as checked_rows,
        countif(d.sigla_uf is null) as missing_rows
    from {{ ref('silver_meta_alfabetizacao_uf') }} as meta
    left join directory_ufs as d on meta.sigla_uf = d.sigla_uf
    where meta.release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_municipio_resultado' as relation_name,
        count(*) as checked_rows,
        countif(resultado.id_municipio is null) as missing_rows
    from {{ ref('silver_meta_alfabetizacao_municipio') }} as meta
    left join {{ ref('silver_municipio') }} as resultado
        on
            meta.release_id = resultado.release_id
            and meta.ano = resultado.ano
            and meta.id_municipio = resultado.id_municipio
            and meta.rede = resultado.rede
    where
        meta.release_id = '{{ var("release_id") }}'
        and meta.rede = 'municipal'
    union all
    select
        'resultado_uf_meta' as relation_name,
        count(*) as checked_rows,
        countif(meta.release_id is null) as missing_rows
    from {{ ref('silver_uf') }} as resultado
    left join metas_uf_escolhidas as meta
        on
            resultado.release_id = meta.release_id
            and resultado.ano = meta.ano_resultado
            and resultado.sigla_uf = meta.sigla_uf
            and resultado.rede = meta.rede
    where
        resultado.release_id = '{{ var("release_id") }}'
        and resultado.rede = 'publica'
)

select
    '{{ var("release_id") }}' as release_id,
    relation_name,
    checked_rows,
    missing_rows
from checks
