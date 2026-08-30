locals {
  jobs = {
    batch = {
      image           = var.images["batch"]
      service_account = var.service_account_emails["batch"]
      command         = var.entrypoints["batch"].command
      args            = var.entrypoints["batch"].args
      timeout         = "3600s"
      retries         = 1
      cpu             = "1"
      memory          = "2Gi"
    }
    dbt = {
      image           = var.images["dbt"]
      service_account = var.service_account_emails["dbt"]
      command         = ["dbt"]
      args            = ["build", "--target", "prod"]
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

  stream_demo_source = templatefile("${path.module}/templates/stream-demo.yaml", {
    project_id             = var.project_id
    region                 = var.region
    producer_job           = "${var.name_prefix}-producer"
    dbt_job                = "${var.name_prefix}-dbt"
    template_gcs_path      = var.dataflow_template_path
    input_subscription     = var.dataflow_subscription_id
    temp_location          = "gs://${var.dataflow_bucket}/temp/"
    staging_location       = "gs://${var.dataflow_bucket}/staging/"
    dataflow_service_email = var.service_account_emails["dataflow"]
    archive_bucket         = var.archive_bucket
    backlog_subscriptions  = jsonencode([for id in var.backlog_subscription_ids : basename(id)])
  })
}

resource "google_cloud_run_v2_job" "job" {
  for_each = local.jobs

  project             = var.project_id
  location            = var.region
  name                = "${var.name_prefix}-${each.key}"
  labels              = var.labels
  deletion_protection = true

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
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "MAXIMUM_BYTES_BILLED"
          value = tostring(var.maximum_bytes_billed)
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
  name   = "templates/municipal-literacy-rate/flex-template.json"
  bucket = var.dataflow_bucket
  content = jsonencode({
    image = var.images["dataflow"]
    sdk_info = {
      language = "PYTHON"
      version  = "2.75.0"
    }
    metadata = {
      name        = "Municipal literacy rate simulated stream"
      description = "Template preparado; nenhum job é iniciado pelo Terraform"
      parameters = [
        { name = "input_subscription", label = "Pub/Sub subscription" },
        { name = "output_table", label = "BigQuery target" },
      ]
    }
  })
}

resource "google_workflows_workflow" "batch" {
  project             = var.project_id
  region              = var.region
  name                = "${var.name_prefix}-monthly-batch"
  description         = "Executa Batch e dbt em sequência; promoção é responsabilidade do dbt"
  service_account     = var.service_account_emails["workflow"]
  labels              = var.labels
  deletion_protection = true

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
  deletion_protection = true

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
    body        = base64encode(jsonencode({ argument = jsonencode({ trigger = "scheduler" }) }))

    oauth_token {
      service_account_email = var.service_account_emails["scheduler"]
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}
