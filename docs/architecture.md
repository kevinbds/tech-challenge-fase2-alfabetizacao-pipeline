# Arquitetura e sequências

## Decisões de desenho

A plataforma é GCP porque BigQuery reduz atrito entre a fonte oficial, o
Warehouse e as verificações de qualidade. Ela não usa uma única ferramenta para
tudo: GCS conserva o Bronze imutável; BigQuery concentra Silver, Gold, operações
e consultas; Cloud Run Jobs executa trabalho finito; Pub/Sub e Dataflow sustentam
a simulação; Workflows coordena estados e Cloud Scheduler só agenda.

O diagrama de componentes está em
[../diagrams/architecture.mmd](../diagrams/architecture.mmd), e as sequências
estão em [../diagrams/sequences.mmd](../diagrams/sequences.mmd).

## Medalhão e fronteiras

| Camada | Local | Finalidade | Acesso |
| --- | --- | --- | --- |
| Landing | GCS | exportação transitória antes da validação | batch-sa; 7 dias |
| Bronze | GCS Parquet Snappy | snapshot original e manifest imutáveis | criador por prefixo; aluno por 730 dias |
| Silver restrito | BigQuery | normalização que ainda contém `id_aluno` | dbt-sa restrita |
| Silver agregado | BigQuery | fatos normalizados sem identificador de aluno | dbt-sa |
| Gold | BigQuery | indicadores, metas, evolução e view híbrida | consumidores autorizados |
| Raw streaming | GCS Avro | evidência técnica de mensagens | dataflow-worker; 30 dias |
| Quarentena/auditoria | BigQuery | rejeições e deduplicação | operação restrita; 30 dias |

`id_aluno` não cruza a fronteira para Gold, logs ou evidências. Identidades de
serviço são separadas para impedir que uma execução de Batch publique no tópico
ou que um produtor leia Silver.

## Batch, releases e recuperação

1. Workflows chama o Job Batch com digest de imagem definido.
2. O Job descobre região/tipos, faz dry-run e interrompe antes de exportar se
   estimar mais que 25 GiB.
3. A consulta calcula `COUNT(*)` e
   `BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(STRUCT(colunas_explicitas))))`.
4. A exportação chega à landing; a validação constrói o Parquet e grava no
   prefixo versionado usando `ifGenerationMatch=0`.
5. O manifest registra reprodução suficiente para reconstituir a decisão.
6. dbt cria um release candidato a partir dos objetos exatos selecionados.
7. Após os testes, uma transação testa que há um único ponteiro em
   `ops.active_release` e atualiza esse ponteiro.
8. Em rollback, a mesma transação aponta para o release anterior; dados Gold e
   Bronze não são apagados.

O arquivo de referência de schema é Parquet zero-row gerado com PyArrow por hash
de schema. Ele fica fora do wildcard de dados e é associado a external tables
por `referenceFileSchemaUri`; Parquet não recebe schema JSON direto nesse caso.

## Streaming e ordem

O evento é validado pelo schema Avro no tópico e, depois, pelas regras de
negócio no pipeline. Pub/Sub entrega ao menos uma vez; por isso a auditoria
guarda mensagens físicas e a deduplicação de negócio escolhe a primeira linha
por `event_id` ordenando `event_time,publish_time,ingestion_time`. Para o
overlay, o desempate é `event_time,publish_time,event_id`.

A assinatura para arquivo GCS grava Avro com metadados, usa o schema do tópico e
rotação de 60 segundos. A assinatura Dataflow é separada. A mensagem inválida
semanticamente não é descartada: segue à quarentena com motivo e correlation ID.
Uma mensagem incompatível com Avro é recusada antes da publicação.

## IAM em termos práticos

| Identidade | Permissão estrita | Não recebe |
| --- | --- | --- |
| terraform-deployer | administrar recursos declarados | Owner, Editor |
| scheduler-sa | invocar workflow | acesso a dados |
| workflow-sa | executar jobs e Dataflow, actAs de runtimes | leitura de aluno |
| batch-sa | jobs BigQuery, landing e criação Bronze condicionada | update/delete Bronze |
| dbt-sa | job BigQuery e escrita Silver/Gold/ops | objeto landing |
| producer-sa | publicar no tópico | leitura de tabelas |
| dataflow-worker | consumir assinatura, gravar raw/Silver | privilégios Terraform |
| archive-sa | criar no prefixo de arquivo | remover objeto |
| CI/Cloud Build | Artifact Registry e actAs pontual | chave estática |

Bindings condicionais limitam prefixos de GCS. Os testes negativos devem provar
que identidades sem finalidade de PII não leem dados restritos e que nenhuma
conta recebe Owner/Editor.

## Sinais operacionais

O sistema publica sucesso/falha de release, idade do último sucesso, volume por
partição, linhas em quarentena, duplicatas, backlog, DLQ, estado Dataflow,
bytes estimados/efetivos e custo projetado. Alertas acionam investigação; não
promovem nem apagam dados automaticamente. O budget é aviso, não hard cap.

