resource "google_project_iam_custom_role" "dataflow_runtime_worker" {
  project     = var.project_id
  role_id     = "alfabetizacaoDataflowRuntimeWorker"
  title       = "Alfabetizacao Dataflow Runtime Worker"
  description = "Executa unidades de trabalho do streaming sem acesso amplo a storage, logs ou métricas"
  permissions = [
    "autoscaling.sites.readRecommendations",
    "autoscaling.sites.writeMetrics",
    "autoscaling.sites.writeState",
    "compute.instanceGroupManagers.update",
    "compute.instances.delete",
    "compute.instances.setDiskAutoDelete",
    "dataflow.jobs.get",
    "dataflow.shuffle.read",
    "dataflow.shuffle.write",
    "dataflow.streamingWorkItems.ImportState",
    "dataflow.streamingWorkItems.commitWork",
    "dataflow.streamingWorkItems.getData",
    "dataflow.streamingWorkItems.getWork",
    "dataflow.streamingWorkItems.getWorkerMetadata",
    "dataflow.workItems.lease",
    "dataflow.workItems.sendMessage",
    "dataflow.workItems.update",
  ]
}

resource "google_project_iam_member" "dataflow_runtime_worker" {
  project = var.project_id
  role    = google_project_iam_custom_role.dataflow_runtime_worker.name
  member  = local.runtime_members["dataflow"]
}

resource "google_project_iam_custom_role" "dataflow_table_writer" {
  project     = var.project_id
  role_id     = local.dataflow_table_writer_role_id
  title       = "Alfabetizacao Dataflow Table Writer"
  description = "Insere eventos somente nas tabelas já criadas para o streaming"
  permissions = ["bigquery.tables.updateData"]
}

resource "google_project_iam_custom_role" "dataflow_bucket_metadata_reader" {
  project     = var.project_id
  role_id     = "alfabetizacaoDataflowBucketMetadataReader"
  title       = "Alfabetizacao Dataflow Bucket Metadata Reader"
  description = "Consulta os metadados do bucket efêmero do Dataflow"
  permissions = ["storage.buckets.get"]
}

resource "google_project_iam_custom_role" "workflow_dataflow_operator" {
  project     = var.project_id
  role_id     = "alfabetizacaoWorkflowDataflowOperator"
  title       = "Alfabetizacao Workflow Dataflow Operator"
  description = "Permite somente as operações de job usadas pela demonstração"
  permissions = [
    "dataflow.jobs.cancel",
    "dataflow.jobs.create",
    "dataflow.jobs.get",
    "dataflow.jobs.list",
    "resourcemanager.projects.get",
  ]
}

resource "google_project_iam_member" "workflow_dataflow_operator" {
  project = var.project_id
  role    = google_project_iam_custom_role.workflow_dataflow_operator.name
  member  = local.runtime_members["workflow"]
}
