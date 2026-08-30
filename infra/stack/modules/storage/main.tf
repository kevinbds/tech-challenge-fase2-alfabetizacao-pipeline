locals {
  buckets = {
    landing = {
      suffix = "landing"
      rules  = [{ age = 7, prefix = ["landing/"] }]
    }
    bronze = {
      suffix = "bronze"
      rules  = [{ age = 730, prefix = ["bronze/alunos/"] }]
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
  name                        = "${var.name_prefix}-${each.value.suffix}"
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
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

  lifecycle {
    prevent_destroy = true
  }
}
