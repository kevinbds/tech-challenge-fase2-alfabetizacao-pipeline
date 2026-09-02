locals {
  log_metrics = {
    batch_failure = {
      description     = "Erros emitidos pelos Cloud Run Jobs Batch, dbt e Producer"
      resource_type   = "cloud_run_job"
      alert           = true
      value_extractor = null
      filter          = "resource.type=\"cloud_run_job\" severity>=ERROR (resource.labels.job_name=\"${var.name_prefix}-batch\" OR resource.labels.job_name=\"${var.name_prefix}-dbt\" OR resource.labels.job_name=\"${var.name_prefix}-producer\")"
    }
    data_quality_critical = {
      description     = "Testes de qualidade reprovados pelo dbt"
      resource_type   = "cloud_run_job"
      alert           = true
      value_extractor = null
      filter          = "resource.type=\"cloud_run_job\" resource.labels.job_name=\"${var.name_prefix}-dbt\" (textPayload=~\"(?i)(failure|error) in test\" OR jsonPayload.message=~\"(?i)(failure|error) in test\" OR jsonPayload.msg=~\"(?i)(failure|error) in test\")"
    }
    batch_processed_rows = {
      description     = "Linhas do manifest concluído que o Batch escreve como JSON no stdout"
      resource_type   = "cloud_run_job"
      alert           = false
      value_extractor = "EXTRACT(jsonPayload.row_count)"
      filter          = "resource.type=\"cloud_run_job\" resource.labels.job_name=\"${var.name_prefix}-batch\" jsonPayload.status=\"completed\" jsonPayload.row_count:*"
    }
    quality_quarantine = {
      description     = "Execuções do modelo de quarentena presentes no stderr/stdout do dbt"
      resource_type   = "cloud_run_job"
      alert           = false
      value_extractor = null
      filter          = "resource.type=\"cloud_run_job\" resource.labels.job_name=\"${var.name_prefix}-dbt\" (textPayload=~\"(?i)quarantine\" OR jsonPayload.message=~\"(?i)quarantine\" OR jsonPayload.msg=~\"(?i)quarantine\")"
    }
    quality_duplicate = {
      description     = "Execuções dos modelos de duplicidade presentes no stderr/stdout do dbt"
      resource_type   = "cloud_run_job"
      alert           = false
      value_extractor = null
      filter          = "resource.type=\"cloud_run_job\" resource.labels.job_name=\"${var.name_prefix}-dbt\" (textPayload=~\"(?i)duplicate\" OR jsonPayload.message=~\"(?i)duplicate\" OR jsonPayload.msg=~\"(?i)duplicate\")"
    }
  }

  subscription_backlog_alerts = {
    archive      = { id = "${var.name_prefix}-raw-archive", duration = "600s" }
    dataflow     = { id = "${var.name_prefix}-dataflow", duration = "600s" }
    dlq_archive  = { id = "${var.name_prefix}-archive-dlq-audit", duration = "60s" }
    dlq_dataflow = { id = "${var.name_prefix}-dataflow-dlq-audit", duration = "60s" }
  }

  dashboard_charts = [
    {
      title   = "Batch - conclusões e linhas processadas"
      filter  = "metric.type=\"logging.googleapis.com/user/${var.name_prefix}-batch_processed_rows\" AND resource.type=\"cloud_run_job\""
      aligner = "ALIGN_SUM"
    },
    {
      title   = "Streaming - volume confirmado"
      filter  = "metric.type=\"pubsub.googleapis.com/subscription/ack_message_count\" AND resource.type=\"pubsub_subscription\" AND resource.label.\"subscription_id\"=\"${var.name_prefix}-dataflow\""
      aligner = "ALIGN_SUM"
    },
    {
      title   = "Streaming - idade da mensagem mais antiga"
      filter  = "metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\" AND resource.type=\"pubsub_subscription\" AND resource.label.\"subscription_id\"=\"${var.name_prefix}-dataflow\""
      aligner = "ALIGN_MAX"
    },
    {
      title   = "dbt - execução do modelo de quarentena"
      filter  = "metric.type=\"logging.googleapis.com/user/${var.name_prefix}-quality_quarantine\" AND resource.type=\"cloud_run_job\""
      aligner = "ALIGN_SUM"
    },
    {
      title   = "dbt - execução dos modelos de duplicidade"
      filter  = "metric.type=\"logging.googleapis.com/user/${var.name_prefix}-quality_duplicate\" AND resource.type=\"cloud_run_job\""
      aligner = "ALIGN_SUM"
    },
  ]
}

resource "google_logging_metric" "pipeline" {
  for_each = local.log_metrics

  project         = var.project_id
  name            = "${var.name_prefix}-${each.key}"
  description     = each.value.description
  filter          = each.value.filter
  value_extractor = each.value.value_extractor

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
  for_each = {
    for key, metric in google_logging_metric.pipeline : key => metric
    if local.log_metrics[key].alert
  }

  project               = var.project_id
  display_name          = "${var.name_prefix}: ${local.log_metrics[each.key].description}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Ao menos uma ocorrência em cinco minutos"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${each.value.name}\" AND resource.type=\"${local.log_metrics[each.key].resource_type}\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  alert_strategy { auto_close = "86400s" }
}

resource "google_monitoring_alert_policy" "dataflow_failure" {
  project               = var.project_id
  display_name          = "${var.name_prefix}: Dataflow em estado terminal de falha"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Dataflow informou falha"
    condition_threshold {
      filter          = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/is_failed\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "workflow_failure" {
  project               = var.project_id
  display_name          = "${var.name_prefix}: execução de Workflow com falha"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Batch ou demonstração de streaming falhou"
    condition_threshold {
      filter          = "metric.type=\"workflows.googleapis.com/finished_execution_count\" AND resource.type=\"workflows.googleapis.com/Workflow\" AND metric.label.\"status\"=\"FAILED\" AND resource.label.\"location\"=\"${var.region}\" AND (resource.label.\"workflow_id\"=\"${module.runtime.workflow_names.batch}\" OR resource.label.\"workflow_id\"=\"${module.runtime.workflow_names.stream_demo}\")"
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "stream_latency" {
  project               = var.project_id
  display_name          = "${var.name_prefix}: latência streaming acima de 60 s"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Mensagem não confirmada há pelo menos 60 s"
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\" AND resource.label.\"subscription_id\"=\"${var.name_prefix}-dataflow\""
      duration        = "300s"
      comparison      = "COMPARISON_GE"
      threshold_value = 60

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "pubsub_backlog" {
  for_each = local.subscription_backlog_alerts

  project               = var.project_id
  display_name          = "${var.name_prefix}: backlog ${each.key}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_email == null ? [] : [google_monitoring_notification_channel.email[0].name]

  conditions {
    display_name = "Backlog acima de zero"
    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.label.\"subscription_id\"=\"${each.value.id}\""
      duration        = each.value.duration
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_dashboard" "pipeline" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "${var.name_prefix}: operação do pipeline"
    mosaicLayout = {
      columns = 12
      tiles = [
        for index, chart in local.dashboard_charts : {
          xPos   = (index % 2) * 6
          yPos   = floor(index / 2) * 4
          width  = 6
          height = 4
          widget = {
            title = chart.title
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = chart.filter
                    aggregation = {
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = chart.aligner
                      crossSeriesReducer = "REDUCE_SUM"
                    }
                  }
                }
              }]
              yAxis = { label = "valor", scale = "LINEAR" }
            }
          }
        }
      ]
    }
  })

  depends_on = [google_logging_metric.pipeline]
}
