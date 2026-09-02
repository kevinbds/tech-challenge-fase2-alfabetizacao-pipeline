module "streaming" {
  source = "./modules/streaming"

  project_id                       = var.project_id
  name_prefix                      = var.name_prefix
  region                           = var.region
  municipal_rate_schema_definition = file("${path.module}/../../schemas/events/MunicipalLiteracyRateUpdatedV1.avsc")
  streaming_bucket                 = module.storage.bucket_names["streaming"]
  archive_service_account_email    = google_service_account.runtime["archive"].email
  labels                           = var.labels

  depends_on = [
    google_project_iam_member.pubsub_service_agent,
    google_storage_bucket_iam_member.archive_creator,
    google_storage_bucket_iam_member.archive_bucket_reader,
    google_service_account_iam_member.pubsub_archive_token_creator,
  ]
}
