output "dataset_ids" {
  value = { for key, dataset in google_bigquery_dataset.layer : key => dataset.dataset_id }
}

output "dataset_delete_contents_on_destroy" {
  value = {
    for key, dataset in google_bigquery_dataset.layer :
    key => dataset.delete_contents_on_destroy
  }
}

output "external_tables" {
  value = { for key, table in google_bigquery_table.external : key => table.id }
}

output "external_contracts" {
  value = {
    for key, table in google_bigquery_table.external : key => {
      dataset_id                = table.dataset_id
      autodetect                = table.external_data_configuration[0].autodetect
      reference_file_schema_uri = table.external_data_configuration[0].reference_file_schema_uri
      source_uris               = table.external_data_configuration[0].source_uris
    }
  }
}

output "release_contract" {
  value = {
    files_table    = "${var.project_id}.${google_bigquery_dataset.layer["ops"].dataset_id}.release_files"
    registry_table = "${var.project_id}.${google_bigquery_dataset.layer["ops"].dataset_id}.release_registry"
    results_table  = "${var.project_id}.${google_bigquery_dataset.layer["quality"].dataset_id}.release_results"
  }
}

output "gold_authorized_views_contract" {
  value = {
    source_datasets = sort([for access in google_bigquery_dataset_access.gold_authorized_views : access.dataset_id])
    view_dataset    = google_bigquery_dataset.layer["gold"].dataset_id
    target_types    = distinct(flatten([for access in google_bigquery_dataset_access.gold_authorized_views : access.dataset[0].target_types]))
  }
}

output "streaming_table_contracts" {
  value = {
    valid = {
      for column in jsondecode(google_bigquery_table.stream_rate.schema) :
      column.name => column.type
    }
    quarantine = {
      for column in jsondecode(google_bigquery_table.stream_quarantine.schema) :
      column.name => column.type
    }
  }
}

output "streaming_table_ids" {
  value = {
    valid      = google_bigquery_table.stream_rate.table_id
    quarantine = google_bigquery_table.stream_quarantine.table_id
  }
}
