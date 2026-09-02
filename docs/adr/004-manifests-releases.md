# ADR 004 — Manifests imutáveis e releases

**Status:** aceito.

Cada exportação recebe fingerprint, hashes, metadados GCS, SHA e digest. Objetos
Bronze usam escrita condicionada; release seleciona snapshot completo e versão
corrigida sem sobrescrever passado.

Alternativas rejeitadas: usar somente data de carga não detecta correção
retroativa; atualizar arquivos por nome fixo destrói auditoria. Trade-off:
armazenamento e metadados crescem, mitigados por lifecycle e teardown.
