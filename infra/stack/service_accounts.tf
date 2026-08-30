locals {
  service_accounts = {
    scheduler = "Invoca somente o workflow mensal"
    workflow  = "Orquestra jobs efêmeros e Dataflow demo"
    batch     = "Extrai e grava landing/Bronze imutável"
    dbt       = "Transforma releases e promove ponteiro"
    producer  = "Publica somente eventos simulados"
    dataflow  = "Executa Beam com até dois workers"
    archive   = "Grava raw Avro pelo Pub/Sub"
  }
}

resource "google_service_account" "runtime" {
  for_each = local.service_accounts

  project      = var.project_id
  account_id   = "${substr(var.name_prefix, 0, 18)}-${each.key}"
  display_name = each.value
}
