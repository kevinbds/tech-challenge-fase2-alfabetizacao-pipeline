# ADR 005 — dbt e promoção transacional

**Status:** aceito.

dbt materializa candidato por release e BigQuery atualiza apenas
ops.active_release em transação após testes. Rollback reposiciona o ponteiro.

Alternativas rejeitadas: views apontando para tabela “latest” são ambíguas;
trocar tabelas por DDL dificulta atomicidade. Trade-off: é necessário manter
ativo e anterior durante a janela de rollback.

