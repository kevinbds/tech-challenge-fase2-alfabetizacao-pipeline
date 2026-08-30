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
          name  = "ALFABETIZACAO_MAX_BYTES_BILLED"
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
        { name = "valid_table", label = "BigQuery valid staging target" },
        { name = "quarantine_table", label = "BigQuery quarantine target" },
        { name = "write_method", label = "BigQuery Storage Write API method" },
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
