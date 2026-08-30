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

variable "region" {
  type        = string
  default     = "southamerica-east1"
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

variable "terraform_deployer_email" {
  type        = string
  default     = null
  nullable    = true
  description = "Conta do bootstrap; nula não cria concessões de deploy."
}

variable "ci_service_account_email" {
  type        = string
  default     = null
  nullable    = true
  description = "Conta CI do bootstrap; nula não cria concessões adicionais."
}

variable "batch_image" {
  type        = string
  description = "Imagem Batch imutável por digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.batch_image))
    error_message = "batch_image deve terminar com @sha256:<64 hex>."
  }
}

variable "dbt_image" {
  type        = string
  description = "Imagem dbt imutável por digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.dbt_image))
    error_message = "dbt_image deve terminar com @sha256:<64 hex>."
  }
}

variable "producer_image" {
  type        = string
  description = "Imagem producer imutável por digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.producer_image))
    error_message = "producer_image deve terminar com @sha256:<64 hex>."
  }
}

variable "dataflow_image" {
  type        = string
  description = "Imagem do SDK Beam/Flex Template imutável por digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.dataflow_image))
    error_message = "dataflow_image deve terminar com @sha256:<64 hex>."
  }
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
    ]) && alltrue([for uri in values(var.reference_schema_uris) : can(regex("^gs://.+/reference/.+\\.parquet$", uri))])
    error_message = "Informe exatamente as seis URIs gs://.../reference/...parquet."
  }
}

variable "scheduler_enabled" {
  type        = bool
  default     = false
  description = "Opt-in explícito para despausar o lote mensal."
}

variable "runtime_entrypoints_verified" {
  type        = bool
  default     = false
  description = "Gate da integração: só libera plano/aplicação depois de validar os entrypoints Batch e Producer no SHA integrado."
}

variable "batch_command" {
  type        = list(string)
  default     = []
  description = "Command do container Batch, preenchido somente pelo gate de integração."
}

variable "batch_args" {
  type        = list(string)
  default     = []
  description = "Argumentos do Batch validados no SHA integrado."
}

variable "producer_command" {
  type        = list(string)
  default     = []
  description = "Command do Producer, preenchido somente pelo gate de integração."
}

variable "producer_args" {
  type        = list(string)
  default     = []
  description = "Argumentos do Producer validados no SHA integrado."
}

variable "maximum_bytes_billed" {
  type        = number
  default     = 26843545600
  description = "Cap de 25 GiB propagado aos jobs."

  validation {
    condition     = var.maximum_bytes_billed > 0 && var.maximum_bytes_billed <= 26843545600
    error_message = "O cap não pode exceder 25 GiB sem mudança deliberada de código."
  }
}

variable "budget_currency" {
  type        = string
  default     = null
  nullable    = true
  description = "Moeda ISO; BRL habilita default 50. Outra moeda exige amount explícito."

  validation {
    condition     = var.budget_currency == null || can(regex("^[A-Z]{3}$", var.budget_currency))
    error_message = "budget_currency deve ser ISO 4217 em maiúsculas."
  }
}

variable "budget_amount" {
  type        = number
  default     = null
  nullable    = true
  description = "Valor do alerta; não é hard cap."

  validation {
    condition     = var.budget_amount == null || var.budget_amount > 0
    error_message = "budget_amount deve ser positivo."
  }
}

variable "deletion_protection" {
  type        = bool
  default     = true
  description = "Proteção explícita das tabelas BigQuery."
}

variable "alert_email" {
  type        = string
  default     = null
  nullable    = true
  description = "E-mail opcional do canal de alertas."
}

variable "labels" {
  type        = map(string)
  description = "Rótulos FinOps comuns."
  default = {
    challenge   = "fiap-fase2"
    environment = "academic"
    managed_by  = "terraform"
  }
}
