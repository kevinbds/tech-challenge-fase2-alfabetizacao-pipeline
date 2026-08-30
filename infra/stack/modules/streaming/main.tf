resource "google_pubsub_schema" "municipal_rate" {
  project = var.project_id
  name    = "${var.name_prefix}-municipal-literacy-rate-v1"
  type    = "AVRO"
  definition = jsonencode({
    type      = "record"
    name      = "MunicipalLiteracyRateUpdatedV1"
    namespace = "br.com.fiap.alfabetizacao.v1"
    fields = [
      { name = "schema_version", type = "string", default = "1.0" },
      { name = "event_id", type = "string" },
      { name = "event_type", type = "string", default = "MunicipalLiteracyRateUpdated" },
      { name = "simulation", type = "boolean", default = true },
      { name = "event_time", type = "string" },
      { name = "ano", type = "int" },
      { name = "id_municipio", type = "string" },
      { name = "rede", type = "string" },
      { name = "taxa_alfabetizacao", type = "double" },
      { name = "taxa_participacao", type = ["null", "double"], default = null },
      { name = "producer", type = "string" },
      { name = "correlation_id", type = "string" },
    ]
  })
}

resource "google_pubsub_topic" "events" {
  project = var.project_id
  name    = "${var.name_prefix}-municipal-rate-events"
  labels  = var.labels

  schema_settings {
    schema   = google_pubsub_schema.municipal_rate.id
    encoding = "JSON"
  }

  message_retention_duration = "86400s"
}

resource "google_pubsub_topic" "dead_letter" {
  for_each = toset(["archive", "dataflow"])

  project = var.project_id
  name    = "${var.name_prefix}-${each.key}-dlq"
  labels  = var.labels
}

resource "google_pubsub_subscription" "raw_archive" {
  project = var.project_id
  name    = "${var.name_prefix}-raw-archive"
  topic   = google_pubsub_topic.events.id
  labels  = var.labels

  ack_deadline_seconds         = 60
  message_retention_duration   = "2592000s"
  retain_acked_messages        = false
  enable_exactly_once_delivery = false

  cloud_storage_config {
    bucket                   = var.streaming_bucket
    filename_prefix          = "raw/"
    filename_suffix          = ".avro"
    filename_datetime_format = "year=YYYY/month=MM/day=DD/hour=hh/mm_ssZ"
    max_duration             = "60s"
    service_account_email    = var.archive_service_account_email

    avro_config {
      write_metadata   = true
      use_topic_schema = true
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter["archive"].id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "60s"
  }
}

resource "google_pubsub_subscription" "dataflow" {
  project = var.project_id
  name    = "${var.name_prefix}-dataflow"
  topic   = google_pubsub_topic.events.id
  labels  = var.labels

  ack_deadline_seconds         = 60
  message_retention_duration   = "2592000s"
  retain_acked_messages        = false
  enable_exactly_once_delivery = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter["dataflow"].id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "60s"
  }
}

resource "google_pubsub_subscription" "dead_letter_audit" {
  for_each = google_pubsub_topic.dead_letter

  project = var.project_id
  name    = "${var.name_prefix}-${each.key}-dlq-audit"
  topic   = each.value.id
  labels  = var.labels

  ack_deadline_seconds       = 60
  message_retention_duration = "2592000s"
  retain_acked_messages      = false
}
