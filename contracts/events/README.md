# Contrato de eventos streaming

`MunicipalLiteracyRateUpdatedV1` é a versão `1.0` do evento sintético usado na demonstração.
O schema Avro controla a compatibilidade de transporte; o modelo Pydantic aplica as regras
semânticas. Os nomes não usam os campos de metadados reservados pelo Pub/Sub (`message_id`,
`publish_time`, `attributes` e `ordering_key`).

A fixture contém dez publicações compatíveis com o schema: oito eventos válidos distintos, a
segunda publicação de um deles e um evento semanticamente inválido. O décimo primeiro registro é
incompatível com Avro e deve ser recusado antes da chamada ao Pub/Sub.
