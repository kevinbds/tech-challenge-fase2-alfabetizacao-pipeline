# FinOps do cenário de demonstração

O comando abaixo produz uma estimativa local, determinística e em BRL. Ele não consulta a conta GCP e não substitui a fatura.

```powershell
uv run python -m alfabetizacao_pipeline.ops.costs estimate --profile demo --format json
```

O perfil fixa BigQuery em `US`; Cloud Run, Dataflow, Cloud Build, Artifact Registry e buckets operacionais em `us-central1`. A cotação de planejamento é US$ 1 = R$ 5,50, revisada em 30/08/2026. Todas as linhas usam preço bruto de lista, sem franquias, créditos, descontos por compromisso ou contratos da conta (`gross_without_free_tier`).

As fontes de preço são as páginas oficiais de [BigQuery](https://cloud.google.com/bigquery/pricing), [Cloud Run](https://cloud.google.com/run/pricing), [Dataflow](https://cloud.google.com/dataflow/pricing), [Cloud Storage](https://cloud.google.com/storage/pricing), [Pub/Sub](https://cloud.google.com/pubsub/pricing), [Workflows](https://cloud.google.com/workflows/pricing), [Cloud Scheduler](https://cloud.google.com/scheduler/pricing), [Artifact Registry](https://cloud.google.com/artifact-registry/pricing), [Cloud Build](https://cloud.google.com/build/pricing-update), [Cloud Observability](https://cloud.google.com/products/observability/pricing) e [rede VPC](https://cloud.google.com/vpc/network-pricing). São preços de lista em USD convertidos pela cotação acima; a moeda faturada e o SKU efetivo da conta podem ser diferentes.

| Componente | Premissa do perfil `demo` | Parcela em BRL |
| --- | --- | ---: |
| BigQuery, consultas | orçamento agregado de 375 GiB processados | R$ 12,59 |
| BigQuery Storage Write API | 0,01 GiB de ingestão | R$ 0,00 |
| BigQuery, storage lógico ativo | 1 GiB-mês | R$ 0,13 |
| Dataflow streaming | dois workers por 35 min; 4 vCPU, 15 GiB e 30 GiB de PD por worker; 1,166666 unidade-hora de Streaming Engine | R$ 2,69 |
| GCS Standard regional | 1,233333 GiB-mês em `us-central1` | R$ 0,14 |
| GCS, operações Class A | 1.000 operações | R$ 0,03 |
| GCS, operações Class B | 1.000 operações | R$ 0,00 |
| Pub/Sub publish/pull, export e retenção | 0,02 GiB de publish/pull, 0,01 GiB para export e 0,000333333 GiB-mês de retenção | R$ 0,00 |
| Cloud Run Jobs | 13 execuções no piso de 60 s: 780 vCPU-s e 1.470 GiB-s | R$ 0,09 |
| Workflows | reserva de 5.000 passos internos | R$ 0,28 |
| Cloud Scheduler | 1 job-mês | R$ 0,55 |
| Artifact Registry | 0,5 GiB-mês | R$ 0,28 |
| Cloud Build, imagens | 12 min no `E2_HIGHCPU_8` | R$ 1,03 |
| Cloud Build, smoke | 4 min no pool default `e2-standard-2` | R$ 0,13 |
| Cloud Logging | 0,05 GiB | R$ 0,14 |
| Cloud Monitoring | 1 MiB de métrica customizada | R$ 1,42 |
| Saída de internet, Premium Tier para América do Sul | zero no caminho controlado | R$ 0,00 |
| Transferência entre regiões, GCP ↔ América do Sul | zero no caminho controlado | R$ 0,00 |
| **Total local do demo** | soma das parcelas já arredondadas a centavos | **R$ 19,50** |

Os valores que arredondam para R$ 0,00 continuam no perfil para não esconder o serviço. `GiB` é usado para dados, logs, rede e armazenamento do Artifact Registry.

## Como a estimativa foi construída

### BigQuery

`bigquery_query_count=243` é uma contagem reproduzível de operações potencialmente faturáveis no caminho de sucesso, não um multiplicador do custo.

| Origem | Operações consideradas |
| --- | ---: |
| Release Batch | 14: `begin`, seis scripts atômicos de snapshot/export/count, um `record` por arquivo Bronze e `complete` |
| `dbt build` da release | 88: 34 modelos, dos quais dois efêmeros incorporados à consulta consumidora, 28 testes de dados e 28 testes unitários (`dbt ls --target offline`) |
| `evaluate_release` e `promote_release` | 2 |
| Demo streaming | 139: uma checagem da release ativa, até 132 polls BigQuery e três modelos mais três testes do seletor `tag:stream_demo` |

Cada uma das seis fontes faz também um dry-run, mas dry-run não processa bytes cobráveis. A inspeção de schema usa a metadata nativa de `get_table()`, sem criar job de consulta. Não há consulta remota de fingerprint: snapshot, `EXPORT DATA` e contagem ocorrem em uma única operação, e o fingerprint é calculado localmente no Parquet exportado. Os 375 GiB são um orçamento agregado prudente para a execução inteira. Não significam que 243 consultas consumirão 25 GiB cada, nem são uma medição observada.

`maximum_bytes_billed` é um teto por consulta quando configurado no Batch, inclusive no controle transacional de release, no perfil dbt e nos polls do workflow. O estimador aceita um total acima de 25 GiB porque o teto individual e o total agregado são medidas diferentes. A premissa de um arquivo Bronze por fonte deve ser atualizada se o export fragmentar arquivos: cada parte acrescenta uma operação `record`.

Beam escreve no BigQuery pela Storage Write API. A reserva de 0,01 GiB usa US$ 0,025/GiB e a de armazenamento lógico ativo, 1 GiB-mês a US$ 0,023/GiB-mês (US$ 0,000031507/GiB-hora, tabela `US`), ou R$ 0,1265/GiB-mês. Ambas são premissas editáveis do perfil, não consumo medido; a primeira ainda arredonda para R$ 0,00. A documentação de [ingestão e armazenamento BigQuery](https://cloud.google.com/bigquery/pricing#data_ingestion_pricing) é a fonte dessas duas linhas.

### Execução, armazenamento e rede

Há três recursos Cloud Run Job (Batch, dbt e Producer), mas 13 execuções no caminho de sucesso: onze no workflow mensal e duas no streaming. Todos têm uma vCPU; Batch e dbt têm 2 GiB, e Producer 0,5 GiB. Cloud Run Jobs é cobrado pelo tempo de vida da instância, com mínimo de um minuto. Em `us-central1`, as taxas brutas aplicadas são US$ 0,000018/vCPU-s e US$ 0,000002/GiB-s, convertidas para R$ 0,000099 e R$ 0,000011. `fail_release` ou rollback não fazem parte do sucesso; cada um adiciona 60 vCPU-s e 120 GiB-s, elevando a linha Cloud Run para cerca de R$ 0,10 antes de novas tentativas.

O template limita Dataflow a um ou dois workers, habilita Streaming Engine e fixa 30 GiB de disco. A página de preço descreve 4 vCPU e 15 GiB para worker streaming; como o template não fixa `machineType` e a documentação de quotas traz outro contexto de default, 4/15 é uma hipótese de sizing, não uma garantia. Os 35 minutos refletem as janelas máximas do workflow: 10 min para `RUNNING`, 10 min para as verificações paralelas e 15 min para `DRAINED`. Tempo adicional de provisionamento e o consumo real precisam ser conferidos nos Resource metrics do Dataflow após a execução.

O GCS operacional é regional em `us-central1`: Standard custa US$ 0,02/GiB-mês, Class A US$ 0,005/1.000 e Class B US$ 0,0004/1.000. Não há replicação inter-região configurada, portanto `gcs_replication_written_gib=0`; a taxa fica no catálogo somente para cenários que a habilitem. Para uma carga mensal de 1 GiB, o perfil reserva 1 GiB persistente em Bronze mais 7/30 GiB no landing, ou 1,233333 GiB-mês. O volume de streaming e dos temporários, além das versões e do soft delete nos buckets protegidos, exige medição separada. O Cloud Storage considera BigQuery `US` equivalente a `us-central1` para leitura do bucket, logo não há transferência regional no caminho-base. A taxa de transferência entre regiões permanece no catálogo para uma mudança futura, mas a quantidade-base é zero. Ela não é egress de internet.

As duas taxas de rede do catálogo têm nomes de campo curtos por compatibilidade com o modelo do estimador, mas não são preços universais. `network_egress_per_gib` representa o egress de internet do Premium Tier com origem em qualquer região Google Cloud e destino na América do Sul: US$ 0,19/GiB no primeiro TiB mensal (R$ 1,045/GiB na cotação do perfil). `cross_region_data_transfer_per_gib` representa egress entre regiões Google Cloud quando uma das pontas é a América do Sul e a outra é qualquer região Google Cloud: US$ 0,14/GiB (R$ 0,77/GiB). A página de rede lista outras combinações e faixas; se a rota mudar, a taxa precisa ser substituída pela linha correspondente, nunca reutilizada como valor genérico. Como o caminho-base não usa nenhuma dessas rotas, as quantidades `network_egress_gib` e `cross_region_data_transfer_gib` permanecem zero e o total continua R$ 19,50.

O tópico tem uma assinatura pull do Dataflow e uma assinatura de export para GCS. Por isso, 0,01 GiB de payload aparece como 0,02 GiB de publish/pull a US$ 40/TiB e como 0,01 GiB de export a US$ 50/TiB. O tópico retém mensagens por 24 horas. As duas assinaturas principais e as duas assinaturas de auditoria da DLQ mantêm mensagens não confirmadas por 30 dias e não preservam mensagens já confirmadas. O perfil supõe que a demonstração drena ou confirma todo o volume em menos de 24 horas; assim, a reserva-base de retenção é 0,01 ÷ 30 GiB-mês a US$ 0,27/GiB-mês. Se houver backlog por mais de um dia, seu volume e duração devem ser medidos e precificados à parte. As três parcelas do caminho-base ainda arredondam para R$ 0,00, mas continuam representadas.

O perfil também fixa `network_egress_gib=0`: a demonstração não publica dados para a internet. Isso não precifica download de novas fontes, clientes BI externos ou qualquer saída introduzida depois. A eventual assinatura ou plano pago da Base dos Dados para 2024/alunos fica fora do custo GCP e depende da conta; não há preço inventado para ela. No preflight humano, confirmar as seis fontes, o ano e o entitlement antes da execução.

Workflows cobra passos internos iniciados em blocos de mil, incluindo `assign`, `switch`, subworkflows, conectores, LROs e polls. A reserva de 5.000 passos cobre os limites atuais: 60 verificações de `RUNNING`, 60 de Silver, 60 de quarentena, 18 tentativas de GCS com até dez páginas, 90 de drain, seis checagens de duplicata, seis de Gold, até 36 ciclos de backlog sobre as duas assinaturas principais e a varredura paginada de encaminhamentos à DLQ depois da barreira de visibilidade, além da lógica e dos polls dos conectores. É uma reserva de planejamento para uma fixture pequena, não telemetria. A franquia mensal oficial de 5.000 passos pode zerar essa linha da fatura, mas foi deliberadamente ignorada.

O submit dispara dois builds no pool default de Iowa. `build-images.yml` escolhe `E2_HIGHCPU_8`: US$ 0,0156/min, ou R$ 0,0858/min. `verify-images.yml` não define `machineType`, por isso usa o default `e2-standard-2`: US$ 0,006/min, ou R$ 0,033/min. A estimativa reserva 12 min para construir as cinco imagens e publicar os descritores, mais 4 min para os oito passos de smoke (nove etapas contando o relatório), totalizando R$ 1,16. São tempos de planejamento, não medição de uma execução remota. Logging é uma reserva de ingestão; `monitoring_mib` representa só métricas customizadas ou derivadas de logs. Métricas nativas de recursos GCP não entram nessa linha.

## Conferência após a execução

Registre evidência operacional separada do manifest: bytes cobrados em jobs do BigQuery, Resource metrics do Dataflow, uso efetivo de Cloud Run e o relatório de cobrança/SKUs. Esses dados distinguem consumo medido de premissas. Antes de aplicar, revisar localização, moeda, tributação, descontos e retenção; depois da avaliação, remover recursos que não precisem permanecer ativos.
