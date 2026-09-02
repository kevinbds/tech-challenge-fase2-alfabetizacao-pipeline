data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service_identity" "pubsub" {
  provider = google-beta
  project  = var.project_id
  service  = "pubsub.googleapis.com"
}

locals {
  pubsub_service_agent = "serviceAccount:${google_project_service_identity.pubsub.email}"
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
    "dbt:staging:roles/bigquery.dataEditor"          = { account = "dbt", dataset = "staging", role = "roles/bigquery.dataEditor" }
    "dbt:silver:roles/bigquery.dataEditor"           = { account = "dbt", dataset = "silver", role = "roles/bigquery.dataEditor" }
    "dbt:restricted-write:roles/bigquery.dataEditor" = { account = "dbt", dataset = "silver_restricted", role = "roles/bigquery.dataEditor" }
    "dbt:gold:roles/bigquery.dataEditor"             = { account = "dbt", dataset = "gold", role = "roles/bigquery.dataEditor" }
    "dbt:gold-internal:roles/bigquery.dataEditor"    = { account = "dbt", dataset = "gold_internal", role = "roles/bigquery.dataEditor" }
    "dbt:ops:roles/bigquery.dataEditor"              = { account = "dbt", dataset = "ops", role = "roles/bigquery.dataEditor" }
    "dbt:quarantine:roles/bigquery.dataEditor"       = { account = "dbt", dataset = "quarantine", role = "roles/bigquery.dataEditor" }
    "dbt:quality:roles/bigquery.dataEditor"          = { account = "dbt", dataset = "quality", role = "roles/bigquery.dataEditor" }
    "workflow:gold:roles/bigquery.dataViewer"        = { account = "workflow", dataset = "gold", role = "roles/bigquery.dataViewer" }
    "workflow:ops:roles/bigquery.dataViewer"         = { account = "workflow", dataset = "ops", role = "roles/bigquery.dataViewer" }
    "workflow:quarantine:roles/bigquery.dataViewer"  = { account = "workflow", dataset = "quarantine", role = "roles/bigquery.dataViewer" }
    "workflow:silver:roles/bigquery.dataViewer"      = { account = "workflow", dataset = "silver", role = "roles/bigquery.dataViewer" }
  }

  dataflow_stream_tables = {
    valid = {
      dataset_id = module.data.dataset_ids["silver"]
      table_id   = module.data.streaming_table_ids.valid
    }
    quarantine = {
      dataset_id = module.data.dataset_ids["quarantine"]
      table_id   = module.data.streaming_table_ids.quarantine
    }
  }
}

resource "google_project_iam_member" "runtime" {
  for_each = local.project_role_bindings

  project = var.project_id
  role    = each.value.role
  member  = local.runtime_members[each.value.account]
}

resource "google_cloud_run_v2_job_iam_member" "workflow_job_executor" {
  for_each = toset(["batch", "dbt", "producer"])

  project  = var.project_id
  location = var.region
  name     = module.runtime.job_names[each.key]
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = local.runtime_members["workflow"]
}

resource "google_project_iam_member" "runtime_artifact_reader" {
  for_each = toset(["batch", "dbt", "producer", "dataflow"])

  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = local.runtime_members[each.key]
}

resource "google_project_iam_member" "gold_consumer_job_user" {
  for_each = var.gold_consumer_principals

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = each.value
}

resource "google_project_iam_member" "pubsub_service_agent" {
  project = var.project_id
  role    = "roles/pubsub.serviceAgent"
  member  = local.pubsub_service_agent
}

resource "google_project_iam_member" "deployer" {
  for_each = var.terraform_deployer_email == null ? toset([]) : local.deployer_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${var.terraform_deployer_email}"
}

resource "google_bigquery_dataset_iam_member" "runtime" {
  for_each = {
    for key, binding in local.dataset_bindings : key => binding
    if !contains(["gold_internal", "ops", "silver"], binding.dataset)
  }

  project    = var.project_id
  dataset_id = module.data.dataset_ids[each.value.dataset]
  role       = each.value.role
  member     = local.runtime_members[each.value.account]
}

resource "google_bigquery_dataset_iam_member" "gold_consumer" {
  for_each = var.gold_consumer_principals

  project    = var.project_id
  dataset_id = module.data.dataset_ids["gold"]
  role       = "roles/bigquery.dataViewer"
  member     = each.value
}

resource "google_bigquery_dataset_access" "runtime" {
  for_each = {
    for key, binding in local.dataset_bindings : key => binding
    if contains(["gold_internal", "ops", "silver"], binding.dataset)
  }

  project       = var.project_id
  dataset_id    = module.data.dataset_ids[each.value.dataset]
  role          = each.value.role
  user_by_email = google_service_account.runtime[each.value.account].email
}

resource "google_bigquery_table_iam_member" "dataflow_stream_writer" {
  for_each = local.dataflow_stream_tables

  project    = var.project_id
  dataset_id = each.value.dataset_id
  table_id   = each.value.table_id
  role       = local.dataflow_table_writer_role_name
  member     = local.runtime_members["dataflow"]

  depends_on = [google_project_iam_custom_role.dataflow_table_writer]
}

resource "google_project_iam_custom_role" "dataflow_dataset_metadata_reader" {
  project     = var.project_id
  role_id     = "alfabetizacaoDataflowDatasetMetadataReader"
  title       = "Alfabetizacao Dataflow Dataset Metadata Reader"
  description = "Permite ao worker resolver somente os metadados dos datasets de saída"
  permissions = ["bigquery.datasets.get"]
}

resource "google_bigquery_dataset_access" "dataflow_silver_metadata_reader" {
  project       = var.project_id
  dataset_id    = module.data.dataset_ids["silver"]
  role          = google_project_iam_custom_role.dataflow_dataset_metadata_reader.name
  user_by_email = google_service_account.runtime["dataflow"].email
}

resource "google_bigquery_dataset_iam_member" "dataflow_quarantine_metadata_reader" {
  project    = var.project_id
  dataset_id = module.data.dataset_ids["quarantine"]
  role       = google_project_iam_custom_role.dataflow_dataset_metadata_reader.name
  member     = local.runtime_members["dataflow"]
}

resource "google_project_iam_custom_role" "workflow_stream_lister" {
  project     = var.project_id
  role_id     = "alfabetizacaoWorkflowStreamLister"
  title       = "Alfabetizacao Workflow Stream Lister"
  description = "Lista nomes de objetos para confirmar o arquivamento do demo"
  permissions = ["storage.objects.list"]
}

resource "google_project_iam_custom_role" "workflow_subscription_reader" {
  project     = var.project_id
  role_id     = "alfabetizacaoWorkflowSubscriptionReader"
  title       = "Alfabetizacao Workflow Subscription Reader"
  description = "Confirma as subscriptions principais do demo"
  permissions = ["pubsub.subscriptions.get"]
}

resource "google_storage_bucket_iam_member" "workflow_stream_observer" {
  bucket = module.storage.bucket_names["streaming"]
  role   = google_project_iam_custom_role.workflow_stream_lister.name
  member = local.runtime_members["workflow"]

  condition {
    title       = "streaming_bucket_list"
    description = "Lista somente nomes no bucket de streaming"
    expression  = "resource.name == 'projects/_/buckets/${module.storage.bucket_names.streaming}'"
  }
}

resource "google_pubsub_subscription_iam_member" "workflow_subscription_reader" {
  for_each = {
    archive  = module.streaming.archive_subscription_id
    dataflow = module.streaming.dataflow_subscription_id
  }

  project      = var.project_id
  subscription = each.value
  role         = google_project_iam_custom_role.workflow_subscription_reader.name
  member       = local.runtime_members["workflow"]
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

resource "google_storage_bucket_iam_member" "dataflow_bucket_viewer" {
  bucket = module.storage.bucket_names["dataflow"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members["dataflow"]
}

resource "google_storage_bucket_iam_member" "workflow_dataflow_bucket_reader" {
  bucket = module.storage.bucket_names["dataflow"]
  role   = "roles/storage.bucketViewer"
  member = local.runtime_members["workflow"]
}

resource "google_service_account_iam_member" "workflow_act_as" {
  for_each = toset(["dataflow"])

  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = local.runtime_members["workflow"]
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
