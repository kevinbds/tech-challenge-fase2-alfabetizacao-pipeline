# ADR 006 — Avro, Pub/Sub e Beam

**Status:** aceito.

Eventos seguem Avro versionado no tópico. Dataflow/Beam valida negócio, deduplica
e grava raw, auditoria, quarentena e Silver. A demo usa DRAIN como término
correto.

Alternativas rejeitadas: JSON sem schema não rejeita a 11ª mensagem antes do
publish; consumidor único sem auditoria não explica redeliveries. Trade-off:
schema e compatibilidade precisam ser evoluídos de forma explícita.

