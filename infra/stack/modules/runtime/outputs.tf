output "job_names" { value = { for key, job in google_cloud_run_v2_job.job : key => job.name } }
output "workflow_names" { value = { batch = google_workflows_workflow.batch.name, stream_demo = google_workflows_workflow.stream_demo.name } }
output "stream_demo_source" {
  description = "Template fonte do Workflow para testes de controle sem execução cloud."
  value       = file("${path.module}/templates/stream-demo.yaml")
}
output "batch_workflow_source" {
  description = "Workflow Batch renderizado para validar overrides sem executar cloud."
  value       = google_workflows_workflow.batch.source_contents
}
output "scheduler_contract" {
  value = {
    paused    = google_cloud_scheduler_job.monthly_batch.paused
    schedule  = google_cloud_scheduler_job.monthly_batch.schedule
    time_zone = google_cloud_scheduler_job.monthly_batch.time_zone
  }
}
output "job_contracts" {
  value = {
    for key, job in google_cloud_run_v2_job.job : key => {
      task_count          = job.template[0].task_count
      parallelism         = job.template[0].parallelism
      timeout             = job.template[0].template[0].timeout
      image               = job.template[0].template[0].containers[0].image
      command             = job.template[0].template[0].containers[0].command
      args                = job.template[0].template[0].containers[0].args
      env                 = { for item in job.template[0].template[0].containers[0].env : item.name => item.value }
      deletion_protection = job.deletion_protection
    }
  }
}
