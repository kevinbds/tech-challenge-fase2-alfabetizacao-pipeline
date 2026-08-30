mock_provider "google" {
  mock_data "google_bigquery_dataset" {
    defaults = { location = "US" }
  }
}

variables {
  project_id              = "fiap-fase2-test"
  source_dataset_location = "US"
  state_bucket_name       = "fiap-fase2-test-tfstate"
  artifacts_bucket_name   = "fiap-fase2-test-artifacts"
  github_repository       = "fiap/equipe-fase2"
  billing_account_id      = "000000-000000-000000"
}

run "bootstrap_contract" {
  command = plan

  assert {
    condition     = google_storage_bucket.terraform_state.versioning[0].enabled
    error_message = "O bucket de estado precisa de versionamento."
  }
  assert {
    condition     = google_storage_bucket.terraform_state.force_destroy == false
    error_message = "O estado não pode ser destruído em cascata."
  }
  assert {
    condition     = google_iam_workload_identity_pool_provider.github[0].attribute_condition == "assertion.repository == 'fiap/equipe-fase2'"
    error_message = "O WIF deve aceitar somente o repositório configurado."
  }
  assert {
    condition     = google_billing_account_iam_member.deployer_costs_manager[0].role == "roles/billing.costsManager"
    error_message = "A permissão de custos deve ficar no billing account."
  }
  assert {
    condition     = output.source_location == "US"
    error_message = "A localização descoberta deve coincidir com a localização declarada."
  }
  assert {
    condition = (
      contains(local.ci_project_roles, "roles/cloudbuild.builds.editor") &&
      contains(local.ci_project_roles, "roles/logging.logWriter") &&
      google_storage_bucket_iam_member.ci_artifact_creator[0].role == "roles/storage.objectCreator"
    )
    error_message = "A identidade CI precisa criar builds, emitir logs e gravar os artefatos do build."
  }
}

run "rejects_source_location_mismatch" {
  command = plan
  variables { source_dataset_location = "southamerica-east1" }
  expect_failures = [check.source_location_matches]
}

run "rejects_malformed_project" {
  command = plan
  variables { project_id = "Projeto Inválido!" }
  expect_failures = [var.project_id]
}

run "rejects_malformed_billing" {
  command = plan
  variables { billing_account_id = "billing-invalido" }
  expect_failures = [var.billing_account_id]
}

run "omits_wif_without_authorized_remote" {
  command = plan
  variables { github_repository = null }
  assert {
    condition     = length(google_iam_workload_identity_pool.github) == 0 && length(google_iam_workload_identity_pool_provider.github) == 0
    error_message = "WIF não pode nascer antes da autorização do remoto."
  }
}

run "teardown_requires_explicit_protection_change" {
  command = plan
  variables { deletion_protection = false }
  assert {
    condition     = google_storage_bucket.terraform_state.force_destroy && google_storage_bucket.artifacts.force_destroy
    error_message = "O teardown dos buckets só pode esvaziá-los após opt-in explícito."
  }
}
