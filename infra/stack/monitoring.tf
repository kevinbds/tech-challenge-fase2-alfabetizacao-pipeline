locals {
  log_metrics = {
    batch_failure = {
      description = "Falhas de Cloud Run Jobs Batch/dbt"
      filter      = "resource.type=\"cloud_run_job\" severity>=ERROR labels.\"challenge\"=\"fiap-fase2\""
    }
    data_quality_critical = {
      description = "Regras críticas de qualidade bloqueando promoção"
      filter      = "jsonPayload.event_type=\"data_quality_result\" jsonPayload.severity=\"critical\""
    }
    dataflow_failure = {
      description = "Falhas ou cancelamento no demo Dataflow"
      filter      = "resource.type=\"dataflow_step\" (jsonPayload.currentState=\"JOB_STATE_FAILED\" OR jsonPayload.currentState=\"JOB_STATE_CANCELLED\")"
    }
  }
}

resource "google_logging_metric" "pipeline" {
  for_each = local.log_metrics

  project     = var.project_id
  name        = "${var.name_prefix}-${each.key}"
  description = each.value.description
  filter      = each.value.filter

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_notification_channel" "email" {
  count = var.alert_email == null ? 0 : 1

  project      = var.project_id
  display_name = "FIAP Fase 2"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "log_failure" {
  for_each = google_logging_metric.pipeline

  project               = var.project_id
  display_name          = "${var.name_prefix}: ${local.log_metrics[each.key].description}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Ao menos uma ocorrência em cinco minutos"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${each.value.name}\" AND resource.type=\"global\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  alert_strategy {
    auto_close = "86400s"
  }
}

resource "google_monitoring_alert_policy" "pubsub_backlog" {
  for_each = {
    archive  = module.streaming.archive_subscription_id
    dataflow = module.streaming.dataflow_subscription_id
  }

  project               = var.project_id
  display_name          = "${var.name_prefix}: backlog ${each.key}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Backlog acima de zero por 10 minutos"
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.label.\"subscription_id\"=\"${basename(each.value)}\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}
