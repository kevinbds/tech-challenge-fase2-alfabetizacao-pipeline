output "resource_inventory" {
  description = "Inventário verificável sem expor segredos nem PII."
  value = {
    buckets                 = module.storage.bucket_names
    datasets                = module.data.dataset_ids
    external_tables         = module.data.external_tables
    cloud_run_jobs          = module.runtime.job_names
    workflows               = module.runtime.workflow_names
    pubsub_topic            = module.streaming.topic_id
    subscriptions           = concat([module.streaming.archive_subscription_id, module.streaming.dataflow_subscription_id], values(module.streaming.dead_letter_subscription_ids))
    service_accounts        = { for key, account in google_service_account.runtime : key => account.email }
    scheduler               = module.runtime.scheduler_contract
    permanent_dataflow_jobs = local.permanent_dataflow_job_count
  }
}

output "security_contract" {
  value = {
    basic_owner_or_editor_grants = [for role in local.all_granted_roles : role if contains(["roles/owner", "roles/editor"], lower(role))]
    restricted_student_dataset   = module.data.dataset_ids["silver_restricted"]
    bronze_student_dataset       = module.data.dataset_ids["bronze_restricted"]
    bronze_batch_can_delete      = false
    deletion_protection          = var.deletion_protection
  }
}

output "external_table_contracts" {
  value = module.data.external_contracts
}

output "streaming_archive_contract" {
  value = module.streaming.archive_contract
}

output "runtime_contract" {
  value = {
    scheduler            = module.runtime.scheduler_contract
    jobs                 = module.runtime.job_contracts
    maximum_bytes_billed = var.maximum_bytes_billed
    dataflow_min_workers = 1
    dataflow_max_workers = 2
    dataflow_experiments = ["enable_portable_runner"]
    permanent_job_count  = local.permanent_dataflow_job_count
  }
}

output "budget_contract" {
  value = local.effective_budget_amount == null ? null : {
    currency = var.budget_currency
    amount   = local.effective_budget_amount
    hard_cap = false
  }
}

output "lifecycle_contracts" {
  value = module.storage.lifecycle_contracts
}

output "silver_alunos_partition_expiration_ms" {
  value = module.data.silver_alunos_partition_expiration_ms
}
