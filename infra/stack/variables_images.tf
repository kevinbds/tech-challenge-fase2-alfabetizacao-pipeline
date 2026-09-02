variable "batch_image" {
  type        = string
  description = "Imagem Batch imutável por digest."
  validation {
    condition = startswith(
      var.batch_image, "${var.region}-docker.pkg.dev/${var.project_id}/"
    ) && can(regex("@sha256:[0-9a-f]{64}$", var.batch_image))
    error_message = "batch_image deve usar o Artifact Registry regional do projeto e digest SHA-256."
  }
}

variable "dbt_image" {
  type        = string
  description = "Imagem dbt imutável por digest."
  validation {
    condition = startswith(
      var.dbt_image, "${var.region}-docker.pkg.dev/${var.project_id}/"
    ) && can(regex("@sha256:[0-9a-f]{64}$", var.dbt_image))
    error_message = "dbt_image deve usar o Artifact Registry regional do projeto e digest SHA-256."
  }
}

variable "producer_image" {
  type        = string
  description = "Imagem producer imutável por digest."
  validation {
    condition = startswith(
      var.producer_image, "${var.region}-docker.pkg.dev/${var.project_id}/"
    ) && can(regex("@sha256:[0-9a-f]{64}$", var.producer_image))
    error_message = "producer_image deve usar o Artifact Registry regional do projeto e digest SHA-256."
  }
}

variable "dataflow_template_image" {
  type        = string
  description = "Imagem launcher do Flex Template imutável por digest."
  validation {
    condition = startswith(
      var.dataflow_template_image, "${var.region}-docker.pkg.dev/${var.project_id}/"
    ) && can(regex("@sha256:[0-9a-f]{64}$", var.dataflow_template_image))
    error_message = "dataflow_template_image deve usar o Artifact Registry regional do projeto e digest SHA-256."
  }
}

variable "dataflow_sdk_image" {
  type        = string
  description = "Imagem SDK Beam dos workers Dataflow imutável por digest e distinta do launcher."
  validation {
    condition = (
      startswith(var.dataflow_sdk_image, "${var.region}-docker.pkg.dev/${var.project_id}/") &&
      can(regex("@sha256:[0-9a-f]{64}$", var.dataflow_sdk_image)) &&
      var.dataflow_sdk_image != var.dataflow_template_image
    )
    error_message = "dataflow_sdk_image deve usar o Artifact Registry regional do projeto, digest SHA-256 e ser distinta de dataflow_template_image."
  }
}

variable "release_git_sha" {
  type        = string
  description = "SHA Git exato do código empacotado nas imagens da release."

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.release_git_sha))
    error_message = "release_git_sha deve conter exatamente 40 caracteres hexadecimais minúsculos."
  }
}
