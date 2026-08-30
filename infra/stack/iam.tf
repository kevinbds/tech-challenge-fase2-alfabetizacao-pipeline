data "google_project" "current" {
  project_id = var.project_id
}

locals {
  pubsub_service_agent = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  runtime_members      = { for key, account in google_service_account.runtime : key => "serviceAccount:${account.email}" }

  project_role_bindings = merge([
    for account, roles in local.project_roles : {
      for role in roles : "${account}:${role}" => {
        account = account
        role    = role
      }
    }
  ]...)

  dataset_bindings = {
    "batch:ops:roles/bigquery.dataEditor"            = { account = "batch", dataset = "ops", role = "roles/bigquery.dataEditor" }
    "dbt:external:roles/bigquery.dataViewer"         = { account = "dbt", dataset = "bronze_external", role = "roles/bigquery.dataViewer" }
    "dbt:restricted-read:roles/bigquery.dataViewer"  = { account = "dbt", dataset = "bronze_restricted", role = "roles/bigquery.dataViewer" }
    "dbt:silver:roles/bigquery.dataEditor"           = { account = "dbt", dataset = "silver", role = "roles/bigquery.dataEditor" }
    "dbt:restricted-write:roles/bigquery.dataEditor" = { account = "dbt", dataset = "silver_restricted", role = "roles/bigquery.dataEditor" }
    "dbt:gold:roles/bigquery.dataEditor"             = { account = "dbt", dataset = "gold", role = "roles/bigquery.dataEditor" }
    "dbt:ops:roles/bigquery.dataEditor"              = { account = "dbt", dataset = "ops", role = "roles/bigquery.dataEditor" }
    "dbt:quarantine:roles/bigquery.dataEditor"       = { account = "dbt", dataset = "quarantine", role = "roles/bigquery.dataEditor" }
    "dataflow:silver:roles/bigquery.dataEditor"      = { account = "dataflow", dataset = "silver", role = "roles/bigquery.dataEditor" }
    "dataflow:ops:roles/bigquery.dataEditor"         = { account = "dataflow", dataset = "ops", role = "roles/bigquery.dataEditor" }
    "dataflow:quarantine:roles/bigquery.dataEditor"  = { account = "dataflow", dataset = "quarantine", role = "roles/bigquery.dataEditor" }
  }
}

resource "google_project_iam_member" "runtime" {
  for_each = local.project_role_bindings

  project = var.project_id
  role    = each.value.role
  member  = local.runtime_members[each.value.account]
}

resource "google_project_iam_member" "runtime_artifact_reader" {
  for_each = toset(["batch", "dbt", "producer", "dataflow"])

  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = local.runtime_members[each.key]
}

resource "google_project_iam_member" "deployer" {
  for_each = var.terraform_deployer_email == null ? toset([]) : local.deployer_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${var.terraform_deployer_email}"
}

resource "google_project_iam_member" "ci_artifact_writer" {
  count = var.ci_service_account_email == null ? 0 : 1

  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${var.ci_service_account_email}"
}

resource "google_bigquery_dataset_iam_member" "runtime" {
  for_each = local.dataset_bindings

  project    = var.project_id
  dataset_id = module.data.dataset_ids[each.value.dataset]
  role       = each.value.role
  member     = local.runtime_members[each.value.account]
}

resource "google_storage_bucket_iam_member" "batch_landing_admin" {
  bucket = module.storage.bucket_names["landing"]
  role   = "roles/storage.objectAdmin"
  member = local.runtime_members["batch"]
}

resource "google_storage_bucket_iam_member" "batch_bronze_creator" {
  bucket = module.storage.bucket_names["bronze"]
  role   = "roles/storage.objectCreator"
  member = local.runtime_members["batch"]

  condition {
    title       = "bronze_immutable_prefix"
    description = "Criação sem update/delete no prefixo Bronze"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["bronze"]}/objects/bronze/')"
  }
}

resource "google_storage_bucket_iam_member" "batch_bronze_viewer" {
  bucket = module.storage.bucket_names["bronze"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members["batch"]

  condition {
    title       = "bronze_validation_prefix"
    description = "Leitura mínima para CRC e validação pós-upload"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["bronze"]}/objects/bronze/')"
  }
}

resource "google_storage_bucket_iam_member" "archive_creator" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.objectCreator"
  member = local.runtime_members["archive"]

  condition {
    title       = "raw_archive_prefix"
    description = "Pub/Sub só cria Avro no raw"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["streaming"]}/objects/raw/')"
  }
}

resource "google_storage_bucket_iam_member" "archive_bucket_reader" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.legacyBucketReader"
  member = local.runtime_members["archive"]
}

resource "google_storage_bucket_iam_member" "workflow_stream_observer" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members["workflow"]
}

resource "google_storage_bucket_iam_member" "dataflow_temp_admin" {
  bucket = module.storage.bucket_names["dataflow"]
  role   = "roles/storage.objectAdmin"
  member = local.runtime_members["dataflow"]

  condition {
    title       = "dataflow_ephemeral_prefixes"
    description = "Admin somente em temp e staging"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["dataflow"]}/objects/temp/') || resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["dataflow"]}/objects/staging/')"
  }
}

resource "google_storage_bucket_iam_member" "runtime_artifacts" {
  for_each = toset(["batch", "dbt", "workflow", "dataflow"])

  bucket = var.artifacts_bucket_name
  role   = "roles/storage.objectViewer"
  member = local.runtime_members[each.key]

  condition {
    title       = "immutable_artifacts"
    description = "Schemas de referência e templates publicados"
    expression  = "resource.name.startsWith('projects/_/buckets/${var.artifacts_bucket_name}/objects/reference/') || resource.name.startsWith('projects/_/buckets/${var.artifacts_bucket_name}/objects/templates/')"
  }
}

resource "google_storage_bucket_iam_member" "runtime_dataflow_templates" {
  for_each = toset(["workflow", "dataflow"])

  bucket = module.storage.bucket_names["dataflow"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members[each.key]

  condition {
    title       = "dataflow_template_prefix"
    description = "Leitura somente do template Flex versionado"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["dataflow"]}/objects/templates/')"
  }
}

resource "google_service_account_iam_member" "workflow_act_as" {
  for_each = toset(["batch", "dbt", "producer", "dataflow"])

  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = local.runtime_members["workflow"]
}

resource "google_service_account_iam_member" "ci_act_as" {
  for_each = var.ci_service_account_email == null ? toset([]) : toset(["batch", "dbt", "producer", "dataflow"])

  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.ci_service_account_email}"
}

resource "google_service_account_iam_member" "pubsub_archive_token_creator" {
  service_account_id = google_service_account.runtime["archive"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.pubsub_service_agent
}

resource "google_project_iam_member" "scheduler_workflow_invoker" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = local.runtime_members["scheduler"]
}

resource "google_pubsub_topic_iam_member" "producer" {
  project = var.project_id
  topic   = module.streaming.topic_name
  role    = "roles/pubsub.publisher"
  member  = local.runtime_members["producer"]
}

resource "google_pubsub_subscription_iam_member" "dataflow_worker" {
  project      = var.project_id
  subscription = module.streaming.dataflow_subscription_id
  role         = "roles/pubsub.subscriber"
  member       = local.runtime_members["dataflow"]
}

resource "google_pubsub_subscription_iam_member" "service_agent_subscriber" {
  for_each = {
    archive  = module.streaming.archive_subscription_id
    dataflow = module.streaming.dataflow_subscription_id
  }

  project      = var.project_id
  subscription = each.value
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_service_agent
}

resource "google_pubsub_topic_iam_member" "service_agent_dlq_publisher" {
  for_each = module.streaming.dead_letter_topic_ids

  project = var.project_id
  topic   = each.value
  role    = "roles/pubsub.publisher"
  member  = local.pubsub_service_agent
}
