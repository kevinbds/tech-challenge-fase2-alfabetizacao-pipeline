output "bucket_names" {
  value = { for key, bucket in google_storage_bucket.data : key => bucket.name }
}

output "bucket_urls" {
  value = { for key, bucket in google_storage_bucket.data : key => bucket.url }
}

output "lifecycle_contracts" {
  value = {
    for key, bucket in google_storage_bucket.data : key => [
      for rule in bucket.lifecycle_rule : {
        age    = one(rule.condition).age
        prefix = one(rule.condition).matches_prefix
        action = one(rule.action).type
      }
    ]
  }
}

output "force_destroy" {
  value = { for key, bucket in google_storage_bucket.data : key => bucket.force_destroy }
}

output "retention_contracts" {
  value = {
    for key, bucket in google_storage_bucket.data : key => {
      versioning_enabled = one(bucket.versioning).enabled
      soft_delete_seconds = (
        length(bucket.soft_delete_policy) == 0
        ? null
        : one(bucket.soft_delete_policy).retention_duration_seconds
      )
    }
  }
}
