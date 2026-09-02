variable "project_id" { type = string }
variable "name_prefix" { type = string }
variable "region" { type = string }
variable "municipal_rate_schema_definition" { type = string }
variable "streaming_bucket" { type = string }
variable "archive_service_account_email" { type = string }
variable "labels" { type = map(string) }
