module "streaming" {
  source = "./modules/streaming"

  project_id                    = var.project_id
  name_prefix                   = var.name_prefix
  streaming_bucket              = module.storage.bucket_names["streaming"]
  archive_service_account_email = google_service_account.runtime["archive"].email
  labels                        = var.labels
}
