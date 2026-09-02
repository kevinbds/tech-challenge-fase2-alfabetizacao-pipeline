variable "project_id" { type = string }
variable "region" { type = string }
variable "data_location" { type = string }
variable "name_prefix" { type = string }
variable "images" { type = map(string) }
variable "service_account_emails" { type = map(string) }
variable "maximum_bytes_billed" { type = number }
variable "scheduler_enabled" { type = bool }
variable "batch_reference_year" {
  type     = number
  nullable = true
}
variable "dataflow_bucket" { type = string }
variable "landing_bucket" { type = string }
variable "bronze_bucket" { type = string }
variable "control_bucket" { type = string }
variable "dataflow_subscription_id" { type = string }
variable "stream_topic_name" { type = string }
variable "archive_bucket" { type = string }
variable "backlog_subscription_ids" { type = list(string) }
variable "labels" { type = map(string) }
variable "deletion_protection" { type = bool }
variable "release_git_sha" { type = string }
variable "entrypoints" {
  type = map(object({
    command = list(string)
    args    = list(string)
  }))
}
