# Bootstrap GCP

Este root começa com estado local. Ele habilita APIs, consulta a localização real da fonte, cria os buckets protegidos, o Artifact Registry e as identidades iniciais. Não execute `apply` até ter projeto, billing e credenciais autorizados.

1. Consulte a fonte: `bq show --format=prettyjson basedosdados:br_inep_avaliacao_alfabetizacao`.
2. Copie `terraform.tfvars.example` para um arquivo local ignorado e preencha os nomes globais.
3. Rode `terraform init`, `terraform plan` e, somente após revisar o plano, autorize o `apply`.
4. Crie `../stack/backend.hcl` a partir do exemplo, usando o output `state_bucket`.
5. No stack, execute `terraform init -migrate-state -backend-config=backend.hcl` somente na migração controlada. Interrupção antes da confirmação não altera o estado remoto; depois, valide `terraform state list` nos dois lados antes de retomar.

O `github_repository` fica nulo até o usuário fornecer `owner/repo`. A condição OIDC impede que outro repositório assuma a conta de CI. `roles/billing.costsManager` é concedida somente no billing account informado, nunca no projeto.
