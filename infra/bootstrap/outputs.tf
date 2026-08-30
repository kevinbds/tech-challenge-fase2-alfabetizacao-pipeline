output "state_bucket" {
  value       = google_storage_bucket.terraform_state.name
  description = "Use este bucket no arquivo backend.hcl do stack."
}

output "artifacts_bucket" {
  value       = google_storage_bucket.artifacts.name
  description = "Bucket de schemas de referência, templates e artefatos assinados."
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
