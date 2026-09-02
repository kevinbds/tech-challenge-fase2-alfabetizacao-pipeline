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

## Arquitetura medalhão e fronteiras

| Camada | Local | Finalidade | Acesso |
| --- | --- | --- | --- |
| Landing | GCS | exportação transitória antes da validação | batch-sa; 7 dias |
| Bronze | GCS Parquet Snappy | snapshot original imutável | criador por prefixo; até o teardown autorizado |
| Controle de release | GCS | manifests e metadados de objetos Bronze | restrito; 730 dias |
| Silver restrito | BigQuery | normalização que ainda contém `id_aluno` | dbt-sa restrita |
| Silver agregado | BigQuery | fatos normalizados sem identificador de aluno | dbt-sa |
| Gold | BigQuery | indicadores, metas, evolução e view híbrida | consumidores autorizados |
| Raw streaming | GCS Avro | evidência técnica de mensagens | export subscription Pub/Sub com `archive-sa`; 30 dias |
| Quarentena | BigQuery | referências, fingerprints e motivos de rejeições de streaming, sem payload | operação restrita; 30 dias |
| Auditoria streaming | BigQuery `ops` | deduplicação de eventos | operação restrita; sem expiração no baseline |

O contrato proíbe `id_aluno` nas saídas modeladas para consumo, em Gold, logs e
evidências. O manifest rejeita o campo literal e há teste estático de ausência
no Gold; como não há redator nem varredura automática de logs no runtime, não há
garantia absoluta de redaction automática: a revisão operacional continua
necessária antes de expor uma evidência. Identidades de serviço são separadas
para impedir que uma execução de Batch publique no tópico ou que um produtor
leia Silver.

## Batch, releases e recuperação

1. Workflows chama o Job Batch com digest de imagem definido.
2. O Job descobre região/tipos, faz dry-run e interrompe antes de exportar se
   estimar mais que 25 GiB.
3. Para cada fonte, um único script BigQuery materializa o snapshot temporário,
   exporta e conta as linhas. Não há consulta remota separada de fingerprint.
4. A exportação constrói o Parquet na landing; a validação confere o arquivo, o
   fingerprint lógico é calculado localmente do Parquet e a cópia para Bronze
   usa `ifGenerationMatch=0`.
5. O manifest registra reprodução suficiente para reconstituir a decisão.
6. dbt cria um release candidato a partir dos objetos exatos selecionados.
   A linha oficial de 2024/RR/rede pública permanece na Silver porque suas metas
   são válidas; a mesma ocorrência também fica registrada na quarentena para
   auditoria e produz aviso no gate e no registro operacional. Qualquer outra
   ausência obrigatória também é registrada na quarentena e bloqueia a promoção.
7. Após os testes, uma transação testa que há um único ponteiro em
   `ops.active_release`, exige que o candidato mantenha o
   `baseline_release_id` ativo e atualiza o ponteiro.
8. Em rollback, a cadeia de baseline define o alvo. Correção histórica exige
   rollback autorizado, promoção da correção e replay cronológico dos anos
   posteriores; os três modelos Gold históricos usam `full_refresh=false`, e
   dados Gold e Bronze não são apagados.

O workflow não distribui segredo de execução. Cada job entra com sua conta de
serviço mínima; estado, baseline e atualização condicional do ponteiro formam o
CAS que fecha corrida e replay dentro da transação.

O arquivo de referência de schema é Parquet zero-row gerado com PyArrow por hash
de schema. Ele fica fora do wildcard de dados e é associado a external tables
por `referenceFileSchemaUri`; Parquet não recebe schema JSON direto nesse caso.

## Streaming e ordem

O evento é validado pelo schema Avro no tópico e, depois, pelas regras de
negócio no pipeline. Beam preserva as nove linhas válidas no staging e envia a
inválida à quarentena; o workflow espera oito `event_id` distintos e um
`event_fingerprint` distinto de quarentena. Como Pub/Sub entrega ao menos uma
vez, após o drain o dbt registra a cópia física na auditoria e escolhe uma linha por `event_id` ordenando
`event_time,publish_time,ingestion_time`. O overlay consome somente essa relação
deduplicada; seu desempate final é `event_time,publish_time,event_id`.

A assinatura para arquivo GCS grava Avro com metadados, usa o schema do tópico e
rotação de 60 segundos. A assinatura Dataflow é separada. A mensagem inválida
semanticamente não é descartada: segue à quarentena com referência da mensagem,
fingerprint, motivo e correlation ID, sem persistir o payload. Uma mensagem
incompatível com Avro é recusada antes da publicação.

## IAM em termos práticos

| Identidade | Permissão estrita | Não recebe |
| --- | --- | --- |
| terraform-deployer | administrar recursos declarados | Owner, Editor |
| scheduler-sa | invocar workflow | acesso a dados |
| workflow-sa | executar apenas os Jobs Batch, dbt e Producer; iniciar Dataflow e actAs apenas de dataflow-worker | payload de aluno, outros Jobs Cloud Run ou identidade dos outros jobs |
| batch-sa | jobs BigQuery, landing e criação Bronze condicionada | update/delete Bronze |
| dbt-sa | job BigQuery e escrita Silver/Gold/ops | objeto landing |
| producer-sa | publicar no tópico | leitura de tabelas |
| dataflow-worker | consumir assinatura, consultar metadados apenas de Silver/quarentena e gravar somente nas duas tabelas do streaming | leitura de dados, escrita no dataset ou privilégios Terraform |
| archive-sa | exportar a assinatura Pub/Sub para o prefixo raw | remover objeto |
| CI/Cloud Build | Artifact Registry e actAs pontual | chave estática |

Bindings condicionais limitam prefixos de GCS. Os testes negativos devem provar
que identidades sem finalidade de PII não leem dados restritos e que nenhuma
conta recebe Owner/Editor.

O papel de metadados do Dataflow contém apenas `bigquery.datasets.get`. Em
Silver, o binding usa o mesmo `google_bigquery_dataset_access` dos authorized
datasets; na quarentena, acompanha os demais `google_bigquery_dataset_iam_member`.
Essa separação evita que dois recursos Terraform disputem a mesma ACL.

Os dois acessos ao plano de controle do Dataflow também são customizados. O
worker recebe somente as permissões de execução descritas no
[papel Worker](https://cloud.google.com/iam/docs/roles-permissions/dataflow#dataflow.worker),
sem repetir storage, logging ou métricas no projeto; esses acessos continuam nos
bindings próprios. `storage.buckets.get`, por exemplo, vem de Bucket Viewer
aplicado somente ao bucket efêmero. O workflow recebe `dataflow.jobs.create`, `get`, `list` e
`cancel`, além de `resourcemanager.projects.get`. Esse conjunto corresponde às
chamadas de lançamento, espera, descoberta e drain/cancel presentes no YAML. A
leitura do template e o `actAs` da conta do worker permanecem vinculados ao
bucket e à service account, respectivamente.

## Sinais operacionais

O Terraform cria alertas para erro dos Cloud Run Jobs, reprovação de teste dbt,
execução FAILED de Workflow, falha terminal do Dataflow, idade da mensagem mais
antiga maior ou igual a 60 segundos sustentada por cinco minutos, backlog das
duas assinaturas principais e backlog das duas DLQs. A falha de Workflow também
cobre etapas antes de existir Dataflow; `is_failed` só cobre um job Dataflow já
lançado. O dashboard
mostra linhas dos manifests Batch concluídos, mensagens confirmadas pelo
Pub/Sub, idade da mensagem mais antiga e execuções dos modelos dbt de quarentena
e duplicidade. Esses dois últimos gráficos contam ocorrências nos logs de
execução dos modelos, não as linhas afetadas.

O runtime ainda não emite a idade do último Batch bem-sucedido nem totais de
linhas quarentenadas e duplicadas. Portanto, não há alerta executável de
freshness em 35 dias nem contadores exatos dessas linhas. Implementá-los exige
um emissor no runtime/dbt ou um avaliador BigQuery agendado; o catálogo não
declara métricas customizadas sem produtor. Alertas apenas iniciam investigação:
não promovem, interrompem ou apagam dados. O budget pertence ao controle FinOps,
com avisos de consumo, e não funciona como hard cap.
