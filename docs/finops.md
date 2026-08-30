# FinOps e controle de custo

## Princípio

Custo é uma condição de execução, não um aviso escondido no fim. O Batch faz
dry-run e falha antes da exportação acima de 25 GiB, salvo autorização explícita.
A plataforma limita workers e timeouts, mantém Cloud Run com mínimo zero e não
sobe Dataflow permanente. O budget notifica: ele não é um disjuntor confiável.

## Estimativa parametrizada

A estimativa é uma fórmula, não uma promessa de preço. Preencha os preços
vigentes da região e moeda do projeto antes do apply.

| Componente | Premissa mensal | Fórmula |
| --- | --- | --- |
| BigQuery consulta | `batch_tib + gold_tib + teste_tib` | TiB processados × preço/TiB |
| GCS | `bronze_gib + raw_gib + artefatos_gib` | GiB-mês por classe × preço/GiB-mês |
| Dataflow demo | `horas_demo × workers × recursos` | recurso-hora × preço regional |
| Cloud Run Jobs | `execuções × duração × recursos` | vCPU-segundo + GiB-segundo |
| Pub/Sub | mensagens/bytes publicados e entregues | volume × preço vigente |
| Observabilidade | métricas, logs e alertas | uso acima de franquia × preço |
| Rede | somente se aplicável | GB de saída × preço |

Arquivo de variáveis deve expor `billing_currency`, `monthly_budget_amount`,
`max_bytes_billed`, `dataflow_max_workers` e retenções. O default 50 só é
aceitável para conta em BRL; não se infere moeda ou orçamento da equipe.

## Governança de gasto

1. executar dry-run e registrar bytes estimados no manifest;
2. abortar acima do teto e pedir autorização para nova tentativa;
3. revisar custo projetado antes de promoção e antes da demo;
4. configurar Budget com alertas para os responsáveis definidos pela equipe;
5. depois da avaliação, fazer teardown em vez de deixar ambientes ociosos.

Risco residual: preço, uso de armazenamento e consultas da fonte podem mudar.
A validação cloud deve capturar o custo real e anexar somente valores agregados,
sem dados de aluno.

