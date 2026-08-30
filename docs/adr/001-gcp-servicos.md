# ADR 001 — GCP e serviços gerenciados

**Status:** aceito.

Usar GCP: BigQuery, GCS, Cloud Run Jobs, Workflows, Scheduler, Pub/Sub, Dataflow,
Monitoring, Budget, Artifact Registry e WIF. A fonte já está em BigQuery, e a
combinação reduz cópia e administração de servidores.

Alternativas rejeitadas: AWS/Azure exigiriam transportar a fonte antes de
analisar; VMs/Kubernetes aumentariam operação de um challenge com jobs finitos.
Trade-off: a validação final depende de billing, IAM e quotas GCP.

