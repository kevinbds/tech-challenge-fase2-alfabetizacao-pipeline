module "runtime" {
  source = "./modules/runtime"

  project_id               = var.project_id
  region                   = var.region
  name_prefix              = var.name_prefix
  images                   = { batch = var.batch_image, dbt = var.dbt_image, producer = var.producer_image, dataflow = var.dataflow_image }
  service_account_emails   = { for key, account in google_service_account.runtime : key => account.email }
  maximum_bytes_billed     = var.maximum_bytes_billed
  scheduler_enabled        = var.scheduler_enabled
  dataflow_bucket          = module.storage.bucket_names["dataflow"]
  dataflow_subscription_id = module.streaming.dataflow_subscription_id
  stream_topic_name        = module.streaming.topic_name
  archive_bucket           = module.storage.bucket_names["streaming"]
  backlog_subscription_ids = concat([module.streaming.archive_subscription_id, module.streaming.dataflow_subscription_id], values(module.streaming.dead_letter_subscription_ids))
  dataflow_template_path   = "gs://${module.storage.bucket_names["dataflow"]}/templates/municipal-literacy-rate/flex-template.json"
  labels                   = var.labels
  deletion_protection      = var.deletion_protection
  release_git_sha          = var.release_git_sha
  entrypoints = {
    batch    = { command = var.batch_command, args = var.batch_args }
    producer = { command = var.producer_command, args = var.producer_args }
  }
}
