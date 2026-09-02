locals {
  required_apis = toset([
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com",
    "bigquerystorage.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "containeranalysis.googleapis.com",
    "compute.googleapis.com",
    "dataflow.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
    "workflows.googleapis.com",
    "workflowexecutions.googleapis.com",
  ])

  deployer_project_roles = toset([
    "roles/artifactregistry.admin",
    "roles/bigquery.admin",
    "roles/cloudscheduler.admin",
    "roles/dataflow.admin",
    "roles/iam.roleAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/logging.configWriter",
    "roles/monitoring.editor",
    "roles/pubsub.admin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/workflows.admin",
  ])

  ci_project_roles = toset([
    "roles/serviceusage.serviceUsageConsumer",
  ])

  cloud_build_project_roles = toset([
    "roles/artifactregistry.writer",
    "roles/logging.logWriter",
    "roles/serviceusage.serviceUsageConsumer",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}

data "google_bigquery_dataset" "source" {
  project    = var.source_project_id
  dataset_id = var.source_dataset_id

  depends_on = [google_project_service.required["bigquery.googleapis.com"]]
}

check "source_location_matches" {
  assert {
    condition     = upper(data.google_bigquery_dataset.source.location) == upper(var.source_dataset_location)
    error_message = "A localização informada não coincide com a fonte. Execute: bq show --format=prettyjson ${var.source_project_id}:${var.source_dataset_id}."
  }
}

resource "google_storage_bucket" "terraform_state" {
  name                        = var.state_bucket_name
  project                     = var.project_id
  location                    = var.region
  force_destroy               = !var.deletion_protection
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]

}

resource "google_storage_bucket" "artifacts" {
  name                        = var.artifacts_bucket_name
  project                     = var.project_id
  location                    = var.region
  force_destroy               = !var.deletion_protection
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.required]

}

resource "google_storage_bucket_iam_member" "ci_artifact_creator" {
  count = var.github_repository == null ? 0 : 1

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_storage_bucket_iam_member" "ci_artifact_viewer" {
  count = var.github_repository == null ? 0 : 1

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_storage_bucket_iam_member" "ci_artifact_bucket_viewer" {
  count = var.github_repository == null ? 0 : 1

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.bucketViewer"
  member = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_storage_bucket_iam_member" "cloud_build_artifact_creator" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_storage_bucket_iam_member" "cloud_build_artifact_viewer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_storage_bucket_iam_member" "cloud_build_artifact_bucket_viewer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.bucketViewer"
  member = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_artifact_registry_repository" "pipeline" {
  project       = var.project_id
  location      = var.region
  repository_id = "alfabetizacao-pipeline"
  description   = "Imagens imutáveis do Tech Challenge FIAP Fase 2"
  format        = "DOCKER"
  labels        = var.labels

  depends_on = [google_project_service.required]
}

resource "google_service_account" "terraform_deployer" {
  project      = var.project_id
  account_id   = "terraform-deployer"
  display_name = "Terraform deployer da Fase 2"

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_service_account" "ci" {
  project      = var.project_id
  account_id   = "pipeline-ci"
  display_name = "CI sem chave estática"

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_service_account" "cloud_build" {
  project      = var.project_id
  account_id   = "pipeline-build"
  display_name = "Cloud Build da Fase 2"

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_project_iam_member" "deployer" {
  for_each = local.deployer_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.terraform_deployer.email}"

  depends_on = [google_project_service.required["cloudresourcemanager.googleapis.com"]]
}

resource "google_project_iam_member" "ci" {
  for_each = local.ci_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.ci.email}"

  depends_on = [google_project_service.required["cloudresourcemanager.googleapis.com"]]
}

resource "google_project_iam_custom_role" "ci_cloud_build_submit" {
  project     = var.project_id
  role_id     = "pipelineCloudBuildSubmit"
  title       = "Pipeline Cloud Build submit and read"
  description = "Permite à identidade CI criar e observar builds sem update ou delete."
  permissions = [
    "cloudbuild.builds.create",
    "cloudbuild.builds.get",
    "cloudbuild.builds.list",
  ]

  depends_on = [
    google_project_service.required["cloudresourcemanager.googleapis.com"],
    google_project_service.required["iam.googleapis.com"],
    google_project_service.required["cloudbuild.googleapis.com"],
  ]
}

resource "google_project_iam_member" "ci_cloud_build_submit" {
  project = var.project_id
  role    = google_project_iam_custom_role.ci_cloud_build_submit.name
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_project_iam_member" "cloud_build" {
  for_each = local.cloud_build_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.cloud_build.email}"

  depends_on = [google_project_service.required["cloudresourcemanager.googleapis.com"]]
}

resource "google_service_account_iam_member" "ci_cloud_build_act_as" {
  count = var.github_repository == null ? 0 : 1

  service_account_id = google_service_account.cloud_build.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_billing_account_iam_member" "deployer_costs_manager" {
  count = var.billing_account_id == null ? 0 : 1

  billing_account_id = var.billing_account_id
  role               = "roles/billing.costsManager"
  member             = "serviceAccount:${google_service_account.terraform_deployer.email}"

  depends_on = [google_project_service.required["cloudbilling.googleapis.com"]]
}

resource "google_iam_workload_identity_pool" "github" {
  count = var.github_repository == null ? 0 : 1

  project                   = var.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "Pool limitado ao repositório autorizado"
  disabled                  = false

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
    google_project_service.required["iamcredentials.googleapis.com"],
    google_project_service.required["cloudresourcemanager.googleapis.com"],
    google_project_service.required["sts.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count = var.github_repository == null ? 0 : 1

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == '${var.github_ref}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_ci" {
  count = var.github_repository == null ? 0 : 1

  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}
