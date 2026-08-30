locals {
  datasets = {
    bronze_external   = { description = "External tables sem identificador de aluno", default_expiration_ms = null }
    bronze_restricted = { description = "External table restrita de alunos", default_expiration_ms = null }
    bronze_current    = { description = "Views filtradas pelo release ativo", default_expiration_ms = null }
    silver            = { description = "Dados normalizados sem PII", default_expiration_ms = null }
    silver_restricted = { description = "Dados pseudonimizados de acesso restrito", default_expiration_ms = 31536000000 }
    gold              = { description = "Indicadores agregados", default_expiration_ms = null }
    ops               = { description = "Metadados, manifests, releases e auditoria", default_expiration_ms = null }
    quarantine        = { description = "Registros inválidos com retenção operacional", default_expiration_ms = 2592000000 }
  }

  external_dataset = {
    for source in var.source_tables : source => source == "alunos" ? "bronze_restricted" : "bronze_external"
  }
}

resource "google_bigquery_dataset" "layer" {
  for_each = local.datasets

  project                     = var.project_id
  dataset_id                  = each.key
  friendly_name               = each.key
  description                 = each.value.description
  location                    = var.location
  delete_contents_on_destroy  = false
  default_table_expiration_ms = each.value.default_expiration_ms
  labels                      = var.labels
  max_time_travel_hours       = 168
}

resource "google_bigquery_table" "external" {
  for_each = var.source_tables

  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer[local.external_dataset[each.key]].dataset_id
  table_id            = each.key
  description         = "Snapshot Parquet imutável; consultar somente pela view filtrada por release"
  deletion_protection = var.deletion_protection
  labels              = var.labels

  external_data_configuration {
    autodetect                = false
    source_format             = "PARQUET"
    source_uris               = ["gs://${var.bronze_bucket}/bronze/${each.key}/*.parquet"]
    reference_file_schema_uri = var.reference_schema_uris[each.key]
  }
}

resource "google_bigquery_table" "active_release" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["ops"].dataset_id
  table_id            = "active_release"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  schema = jsonencode([
    { name = "singleton_key", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "prior_release_id", type = "STRING", mode = "NULLABLE" },
    { name = "promoted_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "release_source_files" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["ops"].dataset_id
  table_id            = "release_source_files"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["release_id", "source_name"]
  schema = jsonencode([
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "source_name", type = "STRING", mode = "REQUIRED" },
    { name = "ano", type = "INTEGER", mode = "NULLABLE" },
    { name = "gcs_uri", type = "STRING", mode = "REQUIRED" },
    { name = "gcs_generation", type = "INTEGER", mode = "REQUIRED" },
    { name = "crc32c", type = "STRING", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "current" {
  for_each = var.source_tables

  project             = var.project_id
  dataset_id          = each.key == "alunos" ? google_bigquery_dataset.layer["silver_restricted"].dataset_id : google_bigquery_dataset.layer["bronze_current"].dataset_id
  table_id            = "${each.key}_current"
  deletion_protection = var.deletion_protection
  labels              = var.labels

  view {
    use_legacy_sql = false
    query          = <<-SQL
      SELECT source.*
      FROM `${var.project_id}.${local.external_dataset[each.key]}.${each.key}` AS source
      WHERE _FILE_NAME IN (
        SELECT file.gcs_uri
        FROM `${var.project_id}.ops.release_source_files` AS file
        JOIN `${var.project_id}.ops.active_release` AS active
          ON active.singleton_key = TRUE
         AND active.release_id = file.release_id
        WHERE file.source_name = '${each.key}'
      )
    SQL
  }

  depends_on = [google_bigquery_table.external, google_bigquery_table.active_release, google_bigquery_table.release_source_files]
}

resource "google_bigquery_table" "silver_alunos" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["silver_restricted"].dataset_id
  table_id            = "alunos"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["release_id", "id_municipio", "rede"]

  time_partitioning {
    type          = "DAY"
    field         = "ano_particao"
    expiration_ms = 31536000000
  }

  schema = jsonencode([
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "ano_particao", type = "DATE", mode = "REQUIRED" },
    { name = "ano", type = "INTEGER", mode = "REQUIRED" },
    { name = "id_municipio", type = "STRING", mode = "REQUIRED" },
    { name = "id_escola", type = "STRING", mode = "REQUIRED" },
    { name = "id_aluno", type = "STRING", mode = "REQUIRED" },
    { name = "rede", type = "STRING", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "stream_quarantine" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["quarantine"].dataset_id
  table_id            = "stream_events"
  deletion_protection = var.deletion_protection
  labels              = var.labels

  time_partitioning {
    type          = "DAY"
    field         = "ingestion_time"
    expiration_ms = 2592000000
  }

  schema = jsonencode([
    { name = "message_id", type = "STRING", mode = "REQUIRED" },
    { name = "reason_code", type = "STRING", mode = "REQUIRED" },
    { name = "ingestion_time", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "stream_rate" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["silver"].dataset_id
  table_id            = "municipal_rate_stream"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["id_municipio", "rede"]

  time_partitioning {
    type          = "DAY"
    field         = "ingestion_time"
    expiration_ms = 2592000000
  }

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED" },
    { name = "message_id", type = "STRING", mode = "REQUIRED" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "publish_time", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "ingestion_time", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "ano", type = "INTEGER", mode = "REQUIRED" },
    { name = "id_municipio", type = "STRING", mode = "REQUIRED" },
    { name = "rede", type = "STRING", mode = "REQUIRED" },
    { name = "taxa_alfabetizacao", type = "NUMERIC", mode = "REQUIRED" },
    { name = "taxa_participacao", type = "NUMERIC", mode = "NULLABLE" },
    { name = "correlation_id", type = "STRING", mode = "REQUIRED" },
    { name = "simulation", type = "BOOLEAN", mode = "REQUIRED" },
  ])
}
