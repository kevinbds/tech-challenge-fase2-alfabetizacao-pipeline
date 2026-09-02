locals {
  datasets = {
    bronze_external   = { description = "External tables sem identificador de aluno", default_expiration_ms = null }
    bronze_restricted = { description = "External table restrita de alunos", default_expiration_ms = null }
    bronze_current    = { description = "Views filtradas pelo release ativo", default_expiration_ms = null }
    staging           = { description = "Views tipadas da release candidata", default_expiration_ms = null }
    silver            = { description = "Dados normalizados sem PII", default_expiration_ms = null }
    silver_restricted = { description = "Dados pseudonimizados de acesso restrito", default_expiration_ms = 31536000000 }
    gold              = { description = "Indicadores agregados", default_expiration_ms = null }
    gold_internal     = { description = "Bases candidatas isoladas por release", default_expiration_ms = null }
    ops               = { description = "Metadados, manifests, releases e auditoria", default_expiration_ms = null }
    quarantine        = { description = "Registros inválidos com retenção operacional", default_expiration_ms = 2592000000 }
    quality           = { description = "Resultados nominais dos gates de release", default_expiration_ms = null }
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
  delete_contents_on_destroy  = !var.deletion_protection
  default_table_expiration_ms = each.value.default_expiration_ms
  labels                      = var.labels
  max_time_travel_hours       = 168
}

resource "google_bigquery_dataset_access" "gold_authorized_views" {
  for_each = toset(["gold_internal", "ops", "silver"])

  project    = var.project_id
  dataset_id = google_bigquery_dataset.layer[each.key].dataset_id

  dataset {
    dataset {
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.layer["gold"].dataset_id
    }
    target_types = ["VIEWS"]
  }
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
    source_uris               = ["gs://${var.bronze_bucket}/bronze/${each.key}/*"]
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

resource "google_bigquery_table" "release_files" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["ops"].dataset_id
  table_id            = "release_files"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["release_id", "table_name"]
  schema = jsonencode([
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "table_name", type = "STRING", mode = "REQUIRED" },
    { name = "ano", type = "INTEGER", mode = "REQUIRED" },
    { name = "file_uri", type = "STRING", mode = "REQUIRED" },
    { name = "source_run_id", type = "STRING", mode = "REQUIRED" },
    { name = "row_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "gcs_generation", type = "INTEGER", mode = "REQUIRED" },
    { name = "crc32c", type = "STRING", mode = "REQUIRED" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "verified_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "release_registry" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["ops"].dataset_id
  table_id            = "release_registry"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["release_id", "status"]
  schema = jsonencode([
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "reference_year", type = "INTEGER", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "completed_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "promoted_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "baseline_release_id", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "release_results" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.layer["quality"].dataset_id
  table_id            = "release_results"
  deletion_protection = var.deletion_protection
  labels              = var.labels
  clustering          = ["release_id", "rule_id"]
  schema = jsonencode([
    { name = "release_id", type = "STRING", mode = "REQUIRED" },
    { name = "rule_id", type = "STRING", mode = "REQUIRED" },
    { name = "metric_value", type = "FLOAT", mode = "NULLABLE" },
    { name = "severity", type = "STRING", mode = "REQUIRED" },
    { name = "action", type = "STRING", mode = "REQUIRED" },
    { name = "details", type = "STRING", mode = "REQUIRED" },
    { name = "evaluated_at", type = "TIMESTAMP", mode = "REQUIRED" },
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
        SELECT file.file_uri
        FROM `${var.project_id}.ops.release_files` AS file
        JOIN `${var.project_id}.ops.active_release` AS active
          ON active.singleton_key = TRUE
         AND active.release_id = file.release_id
        WHERE file.table_name = '${each.key}'
      )
    SQL
  }

  depends_on = [google_bigquery_table.external, google_bigquery_table.active_release, google_bigquery_table.release_files]
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
    { name = "event_fingerprint", type = "STRING", mode = "REQUIRED" },
    { name = "correlation_id", type = "STRING", mode = "NULLABLE" },
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
