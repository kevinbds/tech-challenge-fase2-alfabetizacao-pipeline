# ADR 002 — Lake em GCS e Warehouse em BigQuery

**Status:** aceito.

Guardar snapshots Parquet imutáveis e manifests em GCS (Lake) e transformar,
testar e servir Silver/Gold em BigQuery (Warehouse). Isso conserva a origem
reproduzível sem sacrificar SQL e transações para consumo.

Alternativas rejeitadas: somente BigQuery perde a fronteira clara de arquivo
imutável; somente Data Lake exigiria outro mecanismo de consulta e promoção.
Trade-off: há dois planos de acesso e retenção para governar.
