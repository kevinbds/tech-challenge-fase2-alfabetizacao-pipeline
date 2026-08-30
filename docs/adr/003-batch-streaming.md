# ADR 003 — Batch oficial e streaming simulado

**Status:** aceito.

O resultado oficial entra por Batch mensal; atualizações simuladas entram por
Pub/Sub/Dataflow. A simulação só compõe a view atual quando posterior à promoção
do lote, preservando a história oficial.

Alternativas rejeitadas: streaming para toda fonte oficial não tem justificativa
nem garantia de disponibilidade; sobrescrever o Batch apagaria linhagem.
Trade-off: consumidores precisam entender a diferença entre oficial e simulado.

