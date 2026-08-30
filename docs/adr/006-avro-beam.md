# ADR 006 — Avro, Pub/Sub e Beam

**Status:** aceito.

Eventos seguem Avro versionado no tópico. A assinatura GCS conserva o raw;
Dataflow/Beam valida o negócio e separa staging de quarentena. Depois de DRAINED,
o dbt deduplica por `event_id`, grava a auditoria e atualiza o overlay Silver/Gold.
Essa fronteira mantém a cópia física disponível sem expor duplicata ao consumo.

Alternativas rejeitadas: JSON sem schema não rejeita a 11ª mensagem antes do
publish; consumidor único sem auditoria não explica redeliveries. Trade-off:
schema e compatibilidade precisam ser evoluídos de forma explícita.
