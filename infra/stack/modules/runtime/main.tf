locals {
  jobs = {
    batch = {
      image           = var.images["batch"]
      service_account = var.service_account_emails["batch"]
      command         = var.entrypoints["batch"].command
      args            = var.entrypoints["batch"].args
      timeout         = "3600s"
      retries         = 0
      cpu             = "1"
      memory          = "2Gi"
    }
    dbt = {
      image           = var.images["dbt"]
      service_account = var.service_account_emails["dbt"]
      command         = ["dbt"]
      args            = ["build", "--target", "cloud", "--project-dir", "dbt", "--profiles-dir", "dbt"]
      timeout         = "3600s"
      retries         = 0
      cpu             = "1"
      memory          = "2Gi"
    }
    producer = {
      image           = var.images["producer"]
      service_account = var.service_account_emails["producer"]
      command         = var.entrypoints["producer"].command
      args            = var.entrypoints["producer"].args
      timeout         = "900s"
      retries         = 0
      cpu             = "1"
      memory          = "512Mi"
    }
  }

  stream_demo_source = file("${path.root}/../../workflows/stream_demo.yaml")
  flex_template_metadata = {
    name        = "Municipal literacy rate simulated stream"
    description = "Template preparado; nenhum job é iniciado pelo Terraform"
    streaming   = true
    parameters = [
      {
        name     = "input_subscription"
        label    = "Pub/Sub subscription"
        helpText = "Assinatura Pub/Sub consumida pelo pipeline."
      },
      {
        name     = "valid_table"
        label    = "BigQuery valid staging target"
        helpText = "Tabela BigQuery que recebe eventos válidos."
      },
      {
        name     = "quarantine_table"
        label    = "BigQuery quarantine target"
        helpText = "Tabela BigQuery que recebe eventos rejeitados."
      },
    ]
  }
  flex_template_content = jsonencode({
    image = var.images["dataflow_template"]
    sdkInfo = {
      language = "PYTHON"
      version  = "2.75.0"
    }
    metadata = local.flex_template_metadata
  })
  flex_template_sha256 = sha256(local.flex_template_content)
}

resource "google_cloud_run_v2_job" "job" {
  for_each = local.jobs

  project             = var.project_id
  location            = var.region
  name                = "${var.name_prefix}-${each.key}"
  labels              = var.labels
  deletion_protection = var.deletion_protection

  template {
    parallelism = 1
    task_count  = 1

    template {
      service_account = each.value.service_account
      max_retries     = each.value.retries
      timeout         = each.value.timeout

      containers {
        image   = each.value.image
        command = each.value.command
        args    = each.value.args

        env {
          name  = "ALFABETIZACAO_GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "DBT_LOCATION"
          value = var.data_location
        }

        env {
          name  = "ALFABETIZACAO_BIGQUERY_LOCATION"
          value = var.data_location
        }

        env {
          name  = "ALFABETIZACAO_MAX_BYTES_BILLED"
          value = tostring(var.maximum_bytes_billed)
        }

        env {
          name  = "DBT_MAXIMUM_BYTES_BILLED"
          value = tostring(var.maximum_bytes_billed)
        }

        env {
          name  = "ALFABETIZACAO_GIT_SHA"
          value = var.release_git_sha
        }

        env {
          name  = "ALFABETIZACAO_IMAGE_DIGEST"
          value = each.value.image
        }

        env {
          name  = "ALFABETIZACAO_LANDING_PREFIX"
          value = "gs://${var.landing_bucket}/landing/batch"
        }

        env {
          name  = "ALFABETIZACAO_BRONZE_PREFIX"
          value = "gs://${var.bronze_bucket}/bronze"
        }

        env {
          name  = "ALFABETIZACAO_MANIFEST_PREFIX"
          value = "gs://${var.control_bucket}/manifests"
        }

        env {
          name  = "PUBSUB_TOPIC"
          value = var.stream_topic_name
        }

        resources {
          limits = {
            cpu    = each.value.cpu
            memory = each.value.memory
          }
        }
      }
    }
  }
}

resource "google_storage_bucket_object" "flex_template" {
  name    = "templates/municipal-literacy-rate/${local.flex_template_sha256}.json"
  bucket  = var.dataflow_bucket
  content = local.flex_template_content

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_workflows_workflow" "batch" {
  project             = var.project_id
  region              = var.region
  name                = "${var.name_prefix}-monthly-batch"
  description         = "Executa Batch e dbt em sequência; promoção é responsabilidade do dbt"
  service_account     = var.service_account_emails["workflow"]
  labels              = var.labels
  deletion_protection = var.deletion_protection

  source_contents = templatefile("${path.module}/templates/batch.yaml", {
    project_id = var.project_id
    region     = var.region
    batch_job  = google_cloud_run_v2_job.job["batch"].name
    dbt_job    = google_cloud_run_v2_job.job["dbt"].name
  })
}

resource "google_workflows_workflow" "stream_demo" {
  project             = var.project_id
  region              = var.region
  name                = "${var.name_prefix}-stream-demo"
  description         = "Inicia Flex sob demanda, publica fixture, drena e verifica as duas superfícies"
  service_account     = var.service_account_emails["workflow"]
  labels              = var.labels
  deletion_protection = var.deletion_protection

  user_env_vars = {
    ALFABETIZACAO_FLEX_TEMPLATE_URI            = "gs://${var.dataflow_bucket}/${google_storage_bucket_object.flex_template.name}"
    ALFABETIZACAO_DATAFLOW_SUBSCRIPTION        = var.dataflow_subscription_id
    ALFABETIZACAO_VALID_TABLE                  = "${var.project_id}:silver.municipal_rate_stream"
    ALFABETIZACAO_QUARANTINE_TABLE             = "${var.project_id}:quarantine.stream_events"
    ALFABETIZACAO_DATAFLOW_SERVICE_ACCOUNT     = var.service_account_emails["dataflow"]
    ALFABETIZACAO_DATAFLOW_SDK_CONTAINER_IMAGE = var.images["dataflow_sdk"]
    ALFABETIZACAO_DATAFLOW_TEMP_LOCATION       = "gs://${var.dataflow_bucket}/temp"
    ALFABETIZACAO_DATAFLOW_STAGING_LOCATION    = "gs://${var.dataflow_bucket}/staging"
    ALFABETIZACAO_PRODUCER_JOB                 = google_cloud_run_v2_job.job["producer"].id
    ALFABETIZACAO_TOPIC                        = var.stream_topic_name
    ALFABETIZACAO_RAW_ARCHIVE_BUCKET           = var.archive_bucket
    ALFABETIZACAO_RAW_ARCHIVE_PREFIX           = "raw"
    ALFABETIZACAO_DBT_JOB                      = google_cloud_run_v2_job.job["dbt"].id
    ALFABETIZACAO_MAXIMUM_BYTES_BILLED         = tostring(var.maximum_bytes_billed)
    ALFABETIZACAO_DATA_LOCATION                = var.data_location
    ALFABETIZACAO_GOLD_TABLE                   = "${var.project_id}.gold.indicador_atual_hibrido"
    ALFABETIZACAO_DUPLICATE_AUDIT_TABLE        = "${var.project_id}.ops.stream_event_audit"
    ALFABETIZACAO_BACKLOG_SUBSCRIPTION_IDS     = jsonencode(var.backlog_subscription_ids)
  }

  source_contents = local.stream_demo_source

  depends_on = [google_cloud_run_v2_job.job]
}

resource "google_cloud_scheduler_job" "monthly_batch" {
  project     = var.project_id
  region      = var.region
  name        = "${var.name_prefix}-monthly-batch"
  description = "Primeiro dia do mês às 03:00; nasce desabilitado"
  schedule    = "0 3 1 * *"
  time_zone   = "America/Sao_Paulo"
  paused      = !var.scheduler_enabled

  retry_config {
    retry_count          = 1
    max_retry_duration   = "3600s"
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
    max_doublings        = 3
  }

  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/${google_workflows_workflow.batch.id}/executions"
    body        = base64encode(jsonencode({ argument = jsonencode({ trigger = "scheduler", year = var.batch_reference_year }) }))

    oauth_token {
      service_account_email = var.service_account_emails["scheduler"]
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}
