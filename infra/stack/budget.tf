resource "google_billing_budget" "pipeline" {
  count = local.effective_budget_amount == null ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "${var.name_prefix} academic alert"

  budget_filter {
    projects = ["projects/${data.google_project.current.number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(floor(local.effective_budget_amount))
      nanos         = floor((local.effective_budget_amount - floor(local.effective_budget_amount)) * 1000000000)
    }
  }

  dynamic "threshold_rules" {
    for_each = toset([0.5, 0.8, 1.0])
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
}
