SELECT
    event_id,
    message_id,
    event_time,
    publish_time,
    ingestion_time,
    correlation_id
FROM `{{ project_id }}.{{ silver_dataset }}.stream_valid`
WHERE simulation = TRUE
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY event_id
    ORDER BY event_time DESC, publish_time DESC, ingestion_time DESC
) > 1;
