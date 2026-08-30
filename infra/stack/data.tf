module "data" {
  source = "./modules/data"

  project_id            = var.project_id
  location              = var.data_location
  bronze_bucket         = module.storage.bucket_names["bronze"]
  reference_schema_uris = var.reference_schema_uris
  source_tables         = local.source_tables
  deletion_protection   = var.deletion_protection
  labels                = var.labels
}
