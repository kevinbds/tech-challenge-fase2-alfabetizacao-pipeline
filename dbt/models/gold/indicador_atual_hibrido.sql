{{ config(materialized='view') }}

with release_ativo as (
    select
        release_id,
        promoted_at
    from {{ source('ops', 'active_release') }}
    where singleton_key = true
    qualify count(*) over () = 1
),

lote as (
    select indicador.*
    from {{ ref('indicador_municipio') }} as indicador
    inner join release_ativo on indicador.release_id = release_ativo.release_id
    qualify row_number() over (
        partition by indicador.id_municipio, indicador.rede
        order by indicador.ano desc
    ) = 1
),

eventos_deduplicados as (
    select evento.*
    from {{ source('ops', 'stream_latest') }} as evento
    inner join release_ativo on evento.event_time > release_ativo.promoted_at
    where evento.simulation = true
    qualify row_number() over (
        partition by evento.event_id
        order by evento.event_time desc, evento.publish_time desc, evento.ingestion_time desc
    ) = 1
),

simulacao_atual as (
    select *
    from eventos_deduplicados
    qualify row_number() over (
        partition by ano, id_municipio, rede
        order by event_time desc, publish_time desc, event_id desc
    ) = 1
)

select
    lote.release_id,
    lote.ano,
    lote.ano_particao,
    lote.id_municipio,
    lote.nome_municipio,
    lote.sigla_uf,
    lote.rede,
    simulacao.percentual_participacao,
    simulacao.event_time as atualizado_em,
    coalesce(simulacao.taxa_alfabetizacao, lote.taxa_alfabetizacao) as taxa_alfabetizacao,
    if(simulacao.event_id is null, 'batch_oficial', 'stream_simulacao') as origem
from lote
left join simulacao_atual as simulacao
    on
        lote.ano = simulacao.ano
        and lote.id_municipio = simulacao.id_municipio
        and lote.rede = simulacao.rede
