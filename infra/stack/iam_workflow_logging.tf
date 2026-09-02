resource "google_project_iam_custom_role" "workflow_log_writer" {
  project     = var.project_id
  role_id     = local.workflow_log_writer_role_id
  title       = "Alfabetizacao Workflow Log Writer"
  description = "Registra a falha de limpeza sem ampliar o acesso do Workflow"
  permissions = ["logging.logEntries.create"]
}

resource "google_project_iam_member" "workflow_log_writer" {
  project = var.project_id
  role    = local.workflow_log_writer_role_name
  member  = local.runtime_members["workflow"]

  depends_on = [google_project_iam_custom_role.workflow_log_writer]
}
