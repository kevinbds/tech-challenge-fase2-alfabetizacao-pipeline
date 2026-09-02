locals {
  bucket_prefix = "${var.project_id}-${substr(var.name_prefix, 0, 20)}"
  ephemeral_buckets = toset([
    "landing",
    "streaming",
    "dataflow",
  ])
  buckets = {
    landing = {
      suffix = "landing"
      rules  = [{ age = 7, prefix = ["landing/"] }]
    }
    bronze = {
      suffix = "bronze"
      rules  = []
    }
    control = {
      suffix = "control"
      rules  = [{ age = 730, prefix = ["manifests/"] }]
    }
    streaming = {
      suffix = "streaming"
      rules = [
        { age = 30, prefix = ["raw/"] },
        { age = 30, prefix = ["quarantine/"] },
      ]
    }
    dataflow = {
      suffix = "dataflow"
      rules = [
        { age = 30, prefix = ["temp/"] },
        { age = 30, prefix = ["staging/"] },
      ]
    }
  }
}

resource "google_storage_bucket" "data" {
  for_each = local.buckets

  project                     = var.project_id
  name                        = "${local.bucket_prefix}-${each.value.suffix}"
  location                    = var.location
  force_destroy               = !var.deletion_protection
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = !contains(local.ephemeral_buckets, each.key)
  }

  dynamic "soft_delete_policy" {
    for_each = contains(local.ephemeral_buckets, each.key) ? [true] : []
    content {
      retention_duration_seconds = 0
    }
  }

  dynamic "lifecycle_rule" {
    for_each = each.value.rules
    content {
      action {
        type = "Delete"
      }
      condition {
        age            = lifecycle_rule.value.age
        matches_prefix = lifecycle_rule.value.prefix
      }
    }
  }

}
