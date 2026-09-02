variable "scheduler_enabled" {
  type        = bool
  default     = false
  description = "Opt-in explícito para despausar o lote mensal."

  validation {
    condition     = !var.scheduler_enabled || var.batch_reference_year != null
    error_message = "Habilitar o Scheduler exige batch_reference_year explícito."
  }
}

variable "batch_reference_year" {
  type        = number
  default     = null
  nullable    = true
  description = "Ano de referência enviado pelo Scheduler ao Workflow Batch."

  validation {
    condition = var.batch_reference_year == null ? true : (
      var.batch_reference_year >= 2000
      && var.batch_reference_year <= 2100
      && floor(var.batch_reference_year) == var.batch_reference_year
    )
    error_message = "batch_reference_year deve ser um ano inteiro entre 2000 e 2100."
  }
}

variable "stream_release_year" {
  type        = number
  description = "Ano fixo da fixture streaming, validada contra o recorte oficial de 2024."

  validation {
    condition     = var.stream_release_year == 2024
    error_message = "stream_release_year deve ser 2024, ano coberto pela fixture oficial da demonstração."
  }
}

variable "runtime_entrypoints_verified" {
  type        = bool
  default     = false
  description = "Gate da integração: só libera plano/aplicação depois do smoke de Batch, DBT, Producer e Dataflow no SHA integrado."
}

variable "batch_command" {
  type        = list(string)
  default     = ["alfabetizacao"]
  description = "Executável do container Batch validado no SHA integrado."
}

variable "batch_args" {
  type        = list(string)
  default     = ["batch", "run", "--source", "municipio", "--year", "2024", "--dry-run", "--format", "json"]
  description = "Invocação segura e completa; o Workflow mensal sobrescreve fonte, ano e modo."
}

variable "producer_command" {
  type        = list(string)
  default     = ["python", "-m", "alfabetizacao_pipeline.streaming.producer"]
  description = "Executável standalone do Producer validado no SHA integrado."
}

variable "producer_args" {
  type        = list(string)
  default     = ["--mode", "pubsub", "--fixture", "/app/contracts/events/fixtures/demo.json", "--report", "/tmp/producer-report.json"]
  description = "Argumentos estáticos do Producer; tópico e correlação entram pelo ambiente."
}

variable "maximum_bytes_billed" {
  type        = number
  default     = 26843545600
  description = "Cap de 25 GiB propagado aos jobs."

  validation {
    condition = (
      var.maximum_bytes_billed > 0 &&
      var.maximum_bytes_billed <= 26843545600 &&
      floor(var.maximum_bytes_billed) == var.maximum_bytes_billed
    )
    error_message = "O cap deve ser um inteiro positivo de no máximo 25 GiB."
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
    condition     = var.budget_amount == null ? true : var.budget_amount > 0
    error_message = "budget_amount deve ser positivo."
  }
}

variable "deletion_protection" {
  type        = bool
  default     = true
  description = "Proteção explícita de dados e runtime; desative em apply separado antes do destroy autorizado."
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
