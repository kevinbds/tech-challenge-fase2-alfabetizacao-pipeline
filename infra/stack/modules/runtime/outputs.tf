output "job_names" { value = { for key, job in google_cloud_run_v2_job.job : key => job.name } }
output "workflow_names" { value = { batch = google_workflows_workflow.batch.name, stream_demo = google_workflows_workflow.stream_demo.name } }
output "stream_demo_source" {
  description = "source_contents efetivamente entregue ao Workflow do demo."
  value       = google_workflows_workflow.stream_demo.source_contents
}
output "stream_demo_environment" {
  description = "Constantes imutáveis fornecidas à demonstração streaming."
  value       = google_workflows_workflow.stream_demo.user_env_vars
}
output "batch_workflow_source" {
  description = "Workflow Batch renderizado para validar overrides sem executar cloud."
  value       = google_workflows_workflow.batch.source_contents
}
output "flex_template_content" {
  description = "Contrato estrutural não sensível do ContainerSpec Flex publicado."
  value = {
    container_image    = var.images["dataflow_template"]
    has_sdk_info       = nonsensitive(strcontains(local.flex_template_content, "\"sdkInfo\""))
    has_legacy_sdk_key = nonsensitive(strcontains(local.flex_template_content, "\"sdk_info\""))
    content_sha256     = local.flex_template_sha256
    object_name        = google_storage_bucket_object.flex_template.name
    uri                = "gs://${var.dataflow_bucket}/${google_storage_bucket_object.flex_template.name}"
    supports_streaming = local.flex_template_metadata.streaming
    parameter_help_texts = {
      for parameter in local.flex_template_metadata.parameters :
      parameter.name => parameter.helpText
    }
  }
}
output "scheduler_contract" {
  value = {
    paused         = google_cloud_scheduler_job.monthly_batch.paused
    schedule       = google_cloud_scheduler_job.monthly_batch.schedule
    time_zone      = google_cloud_scheduler_job.monthly_batch.time_zone
    reference_year = var.batch_reference_year
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
