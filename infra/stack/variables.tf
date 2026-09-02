variable "project_id" {
  type        = string
  description = "Projeto GCP de destino."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id deve ser um identificador GCP válido."
  }
}

variable "billing_account_id" {
  type        = string
  description = "Billing account associado ao projeto e ao budget."

  validation {
    condition     = can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account_id))
    error_message = "billing_account_id deve usar o formato 000000-000000-000000."
  }
}

variable "data_location" {
  type        = string
  description = "Localização confirmada da fonte e dos dados. Não deriva de region."

  validation {
    condition     = length(trimspace(var.data_location)) > 0
    error_message = "data_location é obrigatória e deve vir da descoberta do bootstrap."
  }
}

variable "storage_location" {
  type        = string
  default     = "us-central1"
  description = "Região dos buckets operacionais, compatível com o multi-region US do BigQuery."

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.storage_location))
    error_message = "storage_location deve ser uma região GCP válida."
  }
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Região de Cloud Run, Scheduler, Workflows e Dataflow."

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region deve ser uma região GCP válida."
  }
}

variable "name_prefix" {
  type        = string
  default     = "fiap-fase2"
  description = "Prefixo DNS-safe dos recursos."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name_prefix))
    error_message = "name_prefix deve ser DNS-safe e ter de 3 a 31 caracteres."
  }
}

variable "artifacts_bucket_name" {
  type        = string
  description = "Bucket criado pelo bootstrap."
}

variable "gold_consumer_principals" {
  type        = set(string)
  default     = []
  description = "Principais humanos ou de serviço autorizados a consultar somente o dataset Gold."

  validation {
    condition = alltrue([
      for member in var.gold_consumer_principals :
      can(regex("^(user|group|serviceAccount):[^@\\s]+@[^@\\s]+$", member))
    ])
    error_message = "Use members IAM explícitos nos formatos user:, group: ou serviceAccount:."
  }
}

variable "terraform_deployer_email" {
  type        = string
  default     = null
  nullable    = true
  description = "Conta do bootstrap; nula não cria concessões de deploy."
}

variable "reference_schema_uris" {
  type        = map(string)
  description = "URIs imutáveis dos Parquet zero-row, fora do wildcard Bronze."

  validation {
    condition = length(var.reference_schema_uris) == 6 && alltrue([
      for source in [
        "uf",
        "meta_alfabetizacao_brasil",
        "meta_alfabetizacao_uf",
        "meta_alfabetizacao_municipio",
        "municipio",
        "alunos",
      ] : contains(keys(var.reference_schema_uris), source)
      ]) && alltrue([
      for uri in values(var.reference_schema_uris) :
      startswith(uri, "gs://${var.artifacts_bucket_name}/reference/") &&
      can(regex("\\.parquet$", uri))
    ])
    error_message = "Informe exatamente seis Parquet no prefixo reference/ do bucket de artefatos do bootstrap."
  }
}
