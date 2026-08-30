variable "project_id" { type = string }
variable "region" { type = string }
variable "name_prefix" { type = string }
variable "images" { type = map(string) }
variable "service_account_emails" { type = map(string) }
variable "maximum_bytes_billed" { type = number }
variable "scheduler_enabled" { type = bool }
variable "dataflow_bucket" { type = string }
variable "dataflow_subscription_id" { type = string }
variable "stream_topic_name" { type = string }
variable "archive_bucket" { type = string }
variable "backlog_subscription_ids" { type = list(string) }
variable "dataflow_template_path" { type = string }
variable "labels" { type = map(string) }
variable "entrypoints" {
  type = map(object({
    command = list(string)
    args    = list(string)
  }))
}
