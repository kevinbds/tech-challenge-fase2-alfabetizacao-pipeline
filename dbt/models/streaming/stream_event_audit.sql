{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='message_id',
    schema='ops',
    alias='stream_event_audit',
    tags=['stream_demo'],
) }}

with ranked as (
    select
        event_id,
        message_id,
        event_time,
        publish_time,
        ingestion_time,
        correlation_id,
        row_number() over (
            partition by event_id
            order by event_time desc, publish_time desc, ingestion_time desc
        ) as event_rank
    from {{ source('streaming', 'municipal_rate_stream') }}
)

select
    event_id,
    message_id,
    event_time,
    publish_time,
    ingestion_time,
    correlation_id
from ranked
where event_rank > 1
