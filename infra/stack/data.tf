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

data "google_bigquery_dataset" "literacy_source" {
  project    = "basedosdados"
  dataset_id = "br_inep_avaliacao_alfabetizacao"
}

data "google_bigquery_dataset" "territorial_source" {
  project    = "basedosdados"
  dataset_id = "br_bd_diretorios_brasil"
}

check "source_dataset_locations" {
  assert {
    condition = (
      data.google_bigquery_dataset.literacy_source.location == var.data_location &&
      data.google_bigquery_dataset.territorial_source.location == var.data_location
    )
    error_message = "data_location deve coincidir com os datasets públicos de alfabetização e diretório territorial."
  }
}

check "storage_location_is_compatible_with_bigquery" {
  assert {
    condition = (
      var.data_location == "US" &&
      var.storage_location == "us-central1" &&
      var.region == var.storage_location
    )
    error_message = "As fontes estão em BigQuery US; use storage_location e region em us-central1 para evitar egress intercontinental."
  }
}
