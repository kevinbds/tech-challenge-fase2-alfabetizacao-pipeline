# ADR 009 — FinOps e limites operacionais

**Status:** aceito.

Dry-run e cap de 25 GiB barram consulta cara antes da execução. Budget é
parametrizado e alertável; workers, timeouts, drain e mínimo zero limitam a
superfície de custo.

Alternativas rejeitadas: usar budget como hard cap é impreciso; não medir bytes
antes do export expõe o projeto a surpresa de faturamento. Trade-off: cap pode
interromper execução legítima até aprovação humana.
