{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='event_id',
    schema='ops',
    alias='stream_latest',
    tags=['stream_demo'],
) }}

with ranked as (
    select
        event_id,
        event_time,
        publish_time,
        ingestion_time,
        ano,
        id_municipio,
        rede,
        taxa_alfabetizacao,
        taxa_participacao as percentual_participacao,
        simulation,
        row_number() over (
            partition by event_id
            order by event_time desc, publish_time desc, ingestion_time desc
        ) as event_rank
    from {{ source('streaming', 'municipal_rate_stream') }}
)

select
    event_id,
    event_time,
    publish_time,
    ingestion_time,
    ano,
    id_municipio,
    rede,
    taxa_alfabetizacao,
    percentual_participacao,
    simulation
from ranked
where event_rank = 1
