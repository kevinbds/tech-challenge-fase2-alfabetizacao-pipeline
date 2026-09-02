# ADR 008 — Bootstrap Terraform e backend

**Status:** aceito.

Bootstrap usa estado local para criar APIs, bucket de state, artefatos, registry
e WIF. Depois o backend é migrado explicitamente; stack usa esse backend para
o restante da plataforma.

Alternativas rejeitadas: backend manual quebra reprodutibilidade; state local
permanente impede colaboração e recuperação. Trade-off: há uma etapa de migração
que precisa de revisão e autorização antes da execução.
