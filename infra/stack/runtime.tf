module "runtime" {
  source = "./modules/runtime"

  depends_on = [google_project_service_identity.workflows]

  project_id    = var.project_id
  region        = var.region
  data_location = var.data_location
  name_prefix   = var.name_prefix
  images = {
    batch             = var.batch_image
    dbt               = var.dbt_image
    producer          = var.producer_image
    dataflow_template = var.dataflow_template_image
    dataflow_sdk      = var.dataflow_sdk_image
  }
  service_account_emails   = { for key, account in google_service_account.runtime : key => account.email }
  maximum_bytes_billed     = var.maximum_bytes_billed
  scheduler_enabled        = var.scheduler_enabled
  batch_reference_year     = var.batch_reference_year
  landing_bucket           = module.storage.bucket_names["landing"]
  bronze_bucket            = module.storage.bucket_names["bronze"]
  control_bucket           = module.storage.bucket_names["control"]
  dataflow_bucket          = module.storage.bucket_names["dataflow"]
  dataflow_subscription_id = module.streaming.dataflow_subscription_id
  stream_topic_name        = module.streaming.topic_id
  archive_bucket           = module.storage.bucket_names["streaming"]
  backlog_subscription_ids = [module.streaming.archive_subscription_id, module.streaming.dataflow_subscription_id]
  labels                   = var.labels
  deletion_protection      = var.deletion_protection
  release_git_sha          = var.release_git_sha
  entrypoints = {
    batch    = { command = var.batch_command, args = var.batch_args }
    producer = { command = var.producer_command, args = concat(var.producer_args, ["--year", tostring(var.stream_release_year)]) }
  }
}
