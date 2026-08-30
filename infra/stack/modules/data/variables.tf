variable "project_id" { type = string }
variable "location" { type = string }
variable "bronze_bucket" { type = string }
variable "reference_schema_uris" { type = map(string) }
variable "source_tables" { type = set(string) }
variable "deletion_protection" { type = bool }
variable "labels" { type = map(string) }
