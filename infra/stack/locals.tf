locals {
  source_tables = toset([
    "uf",
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "municipio",
    "alunos",
  ])

  effective_budget_amount       = var.budget_amount != null ? var.budget_amount : var.budget_currency == "BRL" ? 50 : null
  permanent_dataflow_job_count  = 0
  dataflow_table_writer_role_id = "alfabetizacaoDataflowTableWriter"
  dataflow_table_writer_role_name = (
    "projects/${var.project_id}/roles/${local.dataflow_table_writer_role_id}"
  )
  workflow_log_writer_role_id = "alfabetizacaoWorkflowLogWriter"
  workflow_log_writer_role_name = (
    "projects/${var.project_id}/roles/${local.workflow_log_writer_role_id}"
  )

  project_roles = {
    batch = toset(["roles/bigquery.jobUser"])
    dbt   = toset(["roles/bigquery.jobUser"])
    workflow = toset([
      "roles/bigquery.jobUser",
      "roles/monitoring.viewer",
    ])
    dataflow = toset([
      "roles/compute.viewer",
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
      "roles/pubsub.serviceAgent",
      "roles/pubsub.subscriber",
      "roles/storage.legacyBucketReader",
      "roles/storage.bucketViewer",
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

check "no_predefined_dataflow_runtime_roles" {
  assert {
    condition = alltrue([
      for role in concat(tolist(local.project_roles.workflow), tolist(local.project_roles.dataflow)) :
      !contains(["roles/dataflow.developer", "roles/dataflow.worker"], role)
    ])
    error_message = "As identidades de runtime devem usar os papéis customizados mínimos do Dataflow."
  }
}

check "dataflow_bigquery_write_contract" {
  assert {
    condition = (
      toset(google_project_iam_custom_role.dataflow_table_writer.permissions) == toset(["bigquery.tables.updateData"]) &&
      toset(keys(google_bigquery_table_iam_member.dataflow_stream_writer)) == toset(["valid", "quarantine"]) &&
      alltrue([
        for binding in values(google_bigquery_table_iam_member.dataflow_stream_writer) :
        binding.role == local.dataflow_table_writer_role_name
      ])
    )
    error_message = "O Dataflow só pode inserir dados nas duas tabelas do streaming pelo papel customizado mínimo."
  }
}
