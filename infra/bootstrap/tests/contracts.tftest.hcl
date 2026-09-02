mock_provider "google" {
  mock_data "google_bigquery_dataset" {
    defaults = { location = "US" }
  }

  mock_resource "google_service_account" {
    defaults = {
      account_id = "pipeline-build"
      email      = "pipeline-build@fiap-fase2-test.iam.gserviceaccount.com"
      name       = "projects/fiap-fase2-test/serviceAccounts/pipeline-build@fiap-fase2-test.iam.gserviceaccount.com"
    }
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
  command = apply

  assert {
    condition     = google_storage_bucket.terraform_state.versioning[0].enabled
    error_message = "O bucket de estado precisa de versionamento."
  }
  assert {
    condition     = google_storage_bucket.terraform_state.force_destroy == false
    error_message = "O estado não pode ser destruído em cascata."
  }
  assert {
    condition     = google_iam_workload_identity_pool_provider.github[0].attribute_condition == "assertion.repository == 'fiap/equipe-fase2' && assertion.ref == 'refs/heads/main'"
    error_message = "O WIF deve aceitar somente o repositório e a ref configurados."
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
    condition     = google_storage_bucket.artifacts.location == "us-central1"
    error_message = "Artefatos de build e Flex devem ficar na mesma região do compute."
  }
  assert {
    condition     = google_storage_bucket.terraform_state.location == "us-central1"
    error_message = "O bucket de estado deve permanecer na região de controle us-central1."
  }
  assert {
    condition = (
      alltrue([for role in local.ci_project_roles : !endswith(role, ".editor")]) &&
      google_project_iam_custom_role.ci_cloud_build_submit.permissions == toset([
        "cloudbuild.builds.create",
        "cloudbuild.builds.get",
        "cloudbuild.builds.list",
      ]) &&
      google_project_iam_member.ci_cloud_build_submit.role == google_project_iam_custom_role.ci_cloud_build_submit.name &&
      contains(local.ci_project_roles, "roles/serviceusage.serviceUsageConsumer") &&
      !contains(local.ci_project_roles, "roles/storage.objectViewer") &&
      google_storage_bucket_iam_member.ci_artifact_creator[0].role == "roles/storage.objectCreator" &&
      google_storage_bucket_iam_member.ci_artifact_viewer[0].role == "roles/storage.objectViewer" &&
      google_storage_bucket_iam_member.ci_artifact_bucket_viewer[0].role == "roles/storage.bucketViewer" &&
      google_service_account_iam_member.ci_cloud_build_act_as[0].role == "roles/iam.serviceAccountUser"
    )
    error_message = "A CI deve iniciar builds, consumir serviços, gravar o staging restrito e assumir somente a conta do build."
  }
  assert {
    condition = (
      google_artifact_registry_repository.pipeline.location == var.region &&
      google_service_account.cloud_build.account_id == "pipeline-build" &&
      contains(local.cloud_build_project_roles, "roles/artifactregistry.writer") &&
      contains(local.cloud_build_project_roles, "roles/serviceusage.serviceUsageConsumer") &&
      google_storage_bucket_iam_member.cloud_build_artifact_creator.role == "roles/storage.objectCreator" &&
      google_storage_bucket_iam_member.cloud_build_artifact_viewer.role == "roles/storage.objectViewer" &&
      google_storage_bucket_iam_member.cloud_build_artifact_bucket_viewer.role == "roles/storage.bucketViewer" &&
      contains(local.required_apis, "compute.googleapis.com") &&
      contains(local.required_apis, "bigquerystorage.googleapis.com") &&
      contains(local.required_apis, "containeranalysis.googleapis.com") &&
      contains(local.required_apis, "workflowexecutions.googleapis.com")
    )
    error_message = "O build precisa publicar no Artifact Registry da mesma região e consumir somente os serviços necessários."
  }
  assert {
    condition     = contains(local.deployer_project_roles, "roles/iam.roleAdmin")
    error_message = "O deployer precisa administrar os custom roles criados pelo stack, inclusive o lister do Workflow."
  }
}

run "rejects_source_location_mismatch" {
  command = apply
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
  command = apply
  variables { github_repository = null }
  assert {
    condition     = length(google_iam_workload_identity_pool.github) == 0 && length(google_iam_workload_identity_pool_provider.github) == 0
    error_message = "WIF não pode nascer antes da autorização do remoto."
  }
}

run "teardown_requires_explicit_protection_change" {
  command = apply
  variables { deletion_protection = false }
  assert {
    condition     = google_storage_bucket.terraform_state.force_destroy && google_storage_bucket.artifacts.force_destroy
    error_message = "O teardown dos buckets só pode esvaziá-los após opt-in explícito."
  }
}
