variable "project_id" {
  description = "Projeto GCP já associado a uma conta de faturamento."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id deve ser um identificador GCP válido, não o nome do projeto."
  }
}

variable "region" {
  description = "Região dos serviços regionais; não define a localização da fonte."
  type        = string
  default     = "southamerica-east1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region deve ser uma região GCP válida."
  }
}

variable "source_project_id" {
  description = "Projeto público que hospeda a fonte."
  type        = string
  default     = "basedosdados"
}

variable "source_dataset_id" {
  description = "Dataset público do indicador 743."
  type        = string
  default     = "br_inep_avaliacao_alfabetizacao"
}

variable "source_dataset_location" {
  description = "Localização esperada da fonte, obtida antes do apply com bq show; nunca é inferida da região."
  type        = string

  validation {
    condition     = length(trimspace(var.source_dataset_location)) > 0
    error_message = "source_dataset_location é obrigatória. Consulte a fonte antes do apply."
  }
}

variable "state_bucket_name" {
  description = "Nome globalmente único do bucket de estado."
  type        = string
}

variable "artifacts_bucket_name" {
  description = "Nome globalmente único do bucket de schemas e templates imutáveis."
  type        = string
}

variable "artifact_registry_location" {
  description = "Localização do Artifact Registry."
  type        = string
  default     = "us"
}

variable "github_repository" {
  description = "Repositório no formato owner/repo. Nulo não cria WIF nem concede acesso externo."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.github_repository == null || can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository deve usar o formato owner/repo."
  }
}

variable "billing_account_id" {
  description = "Billing account para a concessão isolada de costsManager; nulo omite a concessão."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.billing_account_id == null || can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account_id))
    error_message = "billing_account_id deve usar o formato 000000-000000-000000."
  }
}

variable "labels" {
  description = "Rótulos de custo comuns."
  type        = map(string)
  default = {
    challenge   = "fiap-fase2"
    environment = "academic"
    managed_by  = "terraform"
  }
}

variable "deletion_protection" {
  description = "Protege buckets; desative em apply separado antes do destroy autorizado."
  type        = bool
  default     = true
}
