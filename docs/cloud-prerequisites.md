# Pré-requisitos de cloud

O provisionamento foi dividido em `infra/bootstrap` e `infra/stack`. O primeiro
prepara os serviços compartilhados e o backend remoto; o segundo cria os
recursos da plataforma. Nenhum dos dois é aplicado automaticamente.

## Conta e localização

Antes de iniciar, é necessário ter:

- um projeto GCP com faturamento ativo;
- o ID da conta de faturamento;
- uma identidade autorizada a executar Terraform por impersonação, sem chave
  JSON;
- acesso às tabelas utilizadas da Base dos Dados;
- `US` como localização das fontes do BigQuery e `us-central1` como região dos
  buckets, do Artifact Registry e do processamento.

Copie `infra/bootstrap/terraform.tfvars.example` para o arquivo local e ignorado
`infra/bootstrap/terraform.tfvars`. Preencha `project_id`, `region`,
`source_dataset_location`, `billing_account_id` e os nomes globais dos buckets.
Mantenha os valores abaixo, pois eles limitam a federação do GitHub ao
repositório e à branch de produção:

```hcl
github_repository = "kevinbds/tech-challenge-fase2-alfabetizacao-pipeline"
github_ref        = "refs/heads/main"
```

O `billing_account_id` deve ser o mesmo em `infra/bootstrap` e `infra/stack`.
Com `budget_currency` preenchido, o stack cria o orçamento e depende do binding
isolado de `roles/billing.costsManager` configurado pelo bootstrap.

## Validação das fontes

A localização do dataset e a leitura de metadados não garantem acesso às seis
fontes. Antes do `apply` do stack, inspecione cada uma e execute um dry-run com o
ano escolhido:

```bash
export ALFABETIZACAO_GCP_PROJECT_ID='id-do-projeto-de-cobranca'
export ALFABETIZACAO_BIGQUERY_LOCATION='US'
export BATCH_REFERENCE_YEAR=2024

for source in uf meta_alfabetizacao_brasil meta_alfabetizacao_uf \
  meta_alfabetizacao_municipio municipio alunos; do
  uv run alfabetizacao batch source inspect --source "$source" --format json
  uv run alfabetizacao batch plan --source "$source" \
    --year "$BATCH_REFERENCE_YEAR" --dry-run --format json
done

bq --project_id="$ALFABETIZACAO_GCP_PROJECT_ID" query \
  --use_legacy_sql=false --dry_run \
  'SELECT * FROM `basedosdados.br_bd_diretorios_brasil.municipio` LIMIT 0'
```

Se uma consulta falhar por acesso, contratação ou localização, regularize a
fonte antes de criar o stack. Após o provisionamento, repita a prova com as
contas `batch-sa` e `dbt-sa`. A identidade que executa o teste precisa receber
temporariamente `roles/iam.serviceAccountTokenCreator` somente nessas contas; o
papel deve ser removido ao terminar.

## Variáveis do GitHub Actions

O workflow `deploy-gcp` usa o ambiente protegido `production`. Cadastre as oito
variáveis abaixo como **Variables**, não como Secrets:

| Variável | Origem |
| --- | --- |
| `EXPECTED_REPOSITORY_OWNER` | proprietário em `github_repository` |
| `GCP_PROJECT_ID` | `project_id` do bootstrap |
| `GCP_REGION` | `region` do bootstrap |
| `GCP_CLOUD_BUILD_SERVICE_ACCOUNT` | output `cloud_build_service_account_email` |
| `GCP_ARTIFACT_REPOSITORY` | output `artifact_registry_repository_id` |
| `GCP_ARTIFACT_BUCKET` | output `artifacts_bucket` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | output `workload_identity_provider` |
| `GCP_CI_SERVICE_ACCOUNT` | output `ci_service_account_email` |

O workflow constrói e verifica imagens por digest. Ele não executa Terraform e
não inicia cargas Batch ou jobs Dataflow.

## Aprovações operacionais

Revise o plano antes de cada `apply`, migração de state ou teardown. Também
exigem decisão explícita:

- o ano de referência do lote;
- qualquer aumento do limite de 25 GiB por consulta;
- os consumidores autorizados em `gold_consumer_principals`;
- o endereço de alertas, quando `alert_email` for utilizado;
- a promoção ou o rollback de um release;
- a desativação de `deletion_protection` antes de destruir dados.

Os arquivos `terraform.tfvars`, estados locais, credenciais, exports de alunos e
conteúdo de quarentena não devem ser versionados.
