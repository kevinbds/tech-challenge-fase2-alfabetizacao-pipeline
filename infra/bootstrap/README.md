# Bootstrap GCP

Este root começa com estado local. Ele habilita APIs, consulta a localização real da fonte, cria os buckets protegidos, o Artifact Registry e as identidades iniciais. Não execute `apply` até ter projeto, billing e credenciais autorizados.

1. Consulte a fonte: `bq show --format=prettyjson basedosdados:br_inep_avaliacao_alfabetizacao`.
2. Copie `terraform.tfvars.example` para um arquivo local ignorado e preencha os nomes globais e o `billing_account_id` real.
3. Rode `terraform init`, `terraform plan` e, somente após revisar o plano, autorize o `apply`.
4. Crie `../stack/backend.hcl` a partir do exemplo, usando o output `state_bucket`.
5. No stack, use exatamente o mesmo `billing_account_id` no `terraform.tfvars`. O stack cria o budget quando `budget_currency` está definido; com o exemplo em BRL, isso acontece por padrão. O ID não pode ficar `null` no bootstrap nesse caminho: é ele que permite criar o binding isolado `roles/billing.costsManager` para `terraform_deployer` antes do apply do stack.
6. No stack, execute `terraform init -migrate-state -backend-config=backend.hcl` somente na migração controlada. Interrupção antes da confirmação não altera o estado remoto; depois, valide `terraform state list` nos dois lados antes de retomar.

O `github_repository` autorizado é `kevinbds/tech-challenge-fase2-alfabetizacao-pipeline`, e o `github_ref` restringe a identidade CI a `refs/heads/main`. A condição OIDC impede que outro repositório ou outra ref assumam a conta de CI. Quando o stack criar o budget, `billing_account_id` deve ser real e igual nos dois roots; assim `roles/billing.costsManager` é concedida somente no billing account informado, nunca no projeto. Deixar o valor nulo omite esse binding e não é compatível com esse caminho.

O repositório Docker usa sempre a mesma `region` do build (`us-central1` neste
desenho). Após o bootstrap, use os outputs `ci_service_account_email`,
`cloud_build_service_account_email`, `artifact_registry_repository_id`,
`artifacts_bucket` e `workload_identity_provider` para preencher as variáveis do
ambiente protegido no GitHub.

O bootstrap não escolhe pessoas, grupos ou chaves. Antes de executar o stack, um administrador deve conceder `roles/iam.serviceAccountTokenCreator` à identidade humana aprovada, somente sobre o output `terraform_deployer_email`, e essa pessoa deve usar ADC por impersonação: `gcloud auth application-default login --impersonate-service-account=EMAIL_DO_OUTPUT`. Essa concessão é uma dependência humana deliberada; não use chave JSON.

Os buckets nascem com `deletion_protection=true`. No teardown autorizado, só
desative a variável em apply separado depois que o stack tiver sido destruído;
então revise o plano de destroy do bootstrap. Não remova recursos do state para
contornar essa sequência.
