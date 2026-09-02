output "state_bucket" {
  value       = google_storage_bucket.terraform_state.name
  description = "Use este bucket no arquivo backend.hcl do stack."
}

output "artifacts_bucket" {
  value       = google_storage_bucket.artifacts.name
  description = "Bucket de schemas de referência, templates e artefatos do build."
}

output "artifact_registry_repository" {
  value       = google_artifact_registry_repository.pipeline.name
  description = "Repositório Docker; publique imagens por digest antes do stack."
}

output "terraform_deployer_email" {
  value = google_service_account.terraform_deployer.email
}

output "ci_service_account_email" {
  value = google_service_account.ci.email
}

output "cloud_build_service_account_email" {
  value       = google_service_account.cloud_build.email
  description = "Informe este e-mail em GCP_CLOUD_BUILD_SERVICE_ACCOUNT no ambiente protegido do GitHub."
}

output "artifact_registry_repository_id" {
  value       = google_artifact_registry_repository.pipeline.repository_id
  description = "Informe este valor em GCP_ARTIFACT_REPOSITORY no ambiente protegido do GitHub."
}

output "workload_identity_provider" {
  value       = var.github_repository == null ? null : google_iam_workload_identity_pool_provider.github[0].name
  description = "Nulo até o usuário autorizar um repositório GitHub."
}

output "source_location" {
  value       = data.google_bigquery_dataset.source.location
  description = "Localização descoberta e validada da fonte pública."
}

output "migration_command" {
  value       = "terraform -chdir=../stack init -migrate-state -backend-config=backend.hcl"
  description = "Comando documental. Revise backend.hcl e autorize antes de executar."
}
