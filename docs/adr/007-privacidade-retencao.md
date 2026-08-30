# ADR 007 — Privacidade e retenção

**Status:** aceito.

id_aluno é tratado como pseudônimo. Permanece apenas em landing, Bronze,
quarentena e Silver restritos; Gold, logs e evidências usam agregados. Lifecycle
é sete dias em landing, 30 em raw/quarentena, 365 em Silver aluno e 730 em
Bronze aluno.

Alternativas rejeitadas: chamar identificador de anonimizado reduz a proteção;
reter tudo indefinidamente amplia exposição. Trade-off: investigações antigas
podem exigir recuperação da fonte, não retenção de PII sem prazo.

