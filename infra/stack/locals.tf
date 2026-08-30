locals {
  source_tables = toset([
    "uf",
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "municipio",
    "alunos",
  ])

  effective_budget_amount      = var.budget_amount != null ? var.budget_amount : var.budget_currency == "BRL" ? 50 : null
  permanent_dataflow_job_count = 0

  project_roles = {
    batch = toset(["roles/bigquery.jobUser"])
    dbt   = toset(["roles/bigquery.jobUser"])
    workflow = toset([
      "roles/bigquery.jobUser",
      "roles/dataflow.developer",
      "roles/monitoring.viewer",
      "roles/run.jobsExecutorWithOverrides",
    ])
    dataflow = toset([
      "roles/dataflow.worker",
      "roles/logging.logWriter",
      "roles/monitoring.metricWriter",
    ])
  }

  deployer_roles = toset([
    "roles/bigquery.admin",
    "roles/cloudscheduler.admin",
    "roles/dataflow.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/logging.configWriter",
    "roles/monitoring.editor",
    "roles/pubsub.admin",
    "roles/run.admin",
    "roles/storage.admin",
    "roles/workflows.admin",
  ])

  all_granted_roles = concat(
    flatten([for roles in values(local.project_roles) : tolist(roles)]),
    tolist(local.deployer_roles),
    [
      "roles/artifactregistry.reader",
      "roles/artifactregistry.writer",
      "roles/bigquery.dataEditor",
      "roles/bigquery.dataViewer",
      "roles/iam.serviceAccountTokenCreator",
      "roles/iam.serviceAccountUser",
      "roles/pubsub.publisher",
      "roles/pubsub.subscriber",
      "roles/storage.legacyBucketReader",
      "roles/storage.objectAdmin",
      "roles/storage.objectCreator",
      "roles/storage.objectViewer",
      "roles/workflows.invoker",
    ],
  )
}

check "budget_contract" {
  assert {
    condition     = var.budget_currency == null ? var.budget_amount == null : local.effective_budget_amount != null
    error_message = "Defina moeda e valor juntos; somente BRL recebe o default acadêmico de 50."
  }
}

check "no_basic_owner_or_editor" {
  assert {
    condition     = alltrue([for role in local.all_granted_roles : !contains(["roles/owner", "roles/editor"], lower(role))])
    error_message = "roles/owner e roles/editor são proibidos."
  }
}
