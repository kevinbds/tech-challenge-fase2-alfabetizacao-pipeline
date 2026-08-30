MERGE `{{ project_id }}.{{ gold_dataset }}.indicador_streaming_atual` AS current_value
USING (
    SELECT
        event_id,
        event_time,
        publish_time,
        ano,
        id_municipio,
        rede,
        taxa_alfabetizacao,
        participacao,
        simulation
    FROM (
        SELECT
            stream_input.*,
            ROW_NUMBER() OVER (
                PARTITION BY ano, id_municipio, rede
                ORDER BY event_time DESC, publish_time DESC, event_id DESC
            ) AS position
        FROM `{{ project_id }}.{{ silver_dataset }}.stream_valid` AS stream_input
        WHERE simulation = TRUE
    )
    WHERE position = 1
) AS incoming
    ON
        current_value.ano = incoming.ano
        AND current_value.id_municipio = incoming.id_municipio
        AND current_value.rede = incoming.rede
WHEN MATCHED AND incoming.event_time >= current_value.event_time THEN
    UPDATE SET
        event_id = incoming.event_id,
        event_time = incoming.event_time,
        publish_time = incoming.publish_time,
        taxa_alfabetizacao = incoming.taxa_alfabetizacao,
        participacao = incoming.participacao
WHEN NOT MATCHED THEN
    INSERT (
        event_id, event_time, publish_time, ano, id_municipio, rede,
        taxa_alfabetizacao, participacao, simulation
    )
    VALUES (
        incoming.event_id, incoming.event_time, incoming.publish_time, incoming.ano,
        incoming.id_municipio, incoming.rede, incoming.taxa_alfabetizacao,
        incoming.participacao, incoming.simulation
    );
