output "dataset_ids" {
  value = { for key, dataset in google_bigquery_dataset.layer : key => dataset.dataset_id }
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

output "silver_alunos_id" {
  value = google_bigquery_table.silver_alunos.id
}

output "silver_alunos_partition_expiration_ms" {
  value = google_bigquery_table.silver_alunos.time_partitioning[0].expiration_ms
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
