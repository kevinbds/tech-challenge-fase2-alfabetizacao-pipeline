module "storage" {
  source = "./modules/storage"

  project_id  = var.project_id
  location    = var.data_location
  name_prefix = var.name_prefix
  labels      = var.labels
}
