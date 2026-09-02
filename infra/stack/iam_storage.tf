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

resource "google_storage_bucket_iam_member" "batch_control_creator" {
  bucket = module.storage.bucket_names["control"]
  role   = "roles/storage.objectCreator"
  member = local.runtime_members["batch"]
}

resource "google_storage_bucket_iam_member" "batch_control_viewer" {
  bucket = module.storage.bucket_names["control"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members["batch"]
}

resource "google_storage_bucket_iam_member" "dbt_bronze_viewer" {
  bucket = module.storage.bucket_names["bronze"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members["dbt"]
}

resource "google_storage_bucket_iam_member" "dbt_bronze_bucket_reader" {
  bucket = module.storage.bucket_names["bronze"]
  role   = "roles/storage.bucketViewer"
  member = local.runtime_members["dbt"]
}

resource "google_storage_bucket_iam_member" "archive_creator" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.objectCreator"
  member = local.runtime_members["archive"]

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "archive_bucket_reader" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.legacyBucketReader"
  member = local.runtime_members["archive"]
}

resource "google_storage_bucket_iam_member" "pubsub_archive_creator" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.objectCreator"
  member = local.pubsub_service_agent

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "pubsub_archive_bucket_reader" {
  bucket = module.storage.bucket_names["streaming"]
  role   = "roles/storage.legacyBucketReader"
  member = local.pubsub_service_agent
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
  for_each = toset(["workflow"])

  bucket = module.storage.bucket_names["dataflow"]
  role   = "roles/storage.objectViewer"
  member = local.runtime_members[each.key]

  condition {
    title       = "dataflow_template_prefix"
    description = "Leitura somente do template Flex versionado"
    expression  = "resource.name.startsWith('projects/_/buckets/${module.storage.bucket_names["dataflow"]}/objects/templates/')"
  }
}

resource "google_storage_bucket_iam_member" "dataflow_bucket_reader" {
  bucket = module.storage.bucket_names["dataflow"]
  role   = google_project_iam_custom_role.dataflow_bucket_metadata_reader.name
  member = local.runtime_members["dataflow"]
}
