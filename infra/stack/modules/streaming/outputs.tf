output "topic_id" { value = google_pubsub_topic.events.id }
output "topic_name" { value = google_pubsub_topic.events.name }
output "schema_definition" { value = google_pubsub_schema.municipal_rate.definition }
output "topic_encoding" { value = google_pubsub_topic.events.schema_settings[0].encoding }
output "topic_persistence_regions" { value = google_pubsub_topic.events.message_storage_policy[0].allowed_persistence_regions }
output "dead_letter_persistence_regions" {
  value = {
    for key, topic in google_pubsub_topic.dead_letter :
    key => topic.message_storage_policy[0].allowed_persistence_regions
  }
}
output "dataflow_subscription_id" { value = google_pubsub_subscription.dataflow.id }
output "archive_subscription_id" { value = google_pubsub_subscription.raw_archive.id }
output "dead_letter_topic_ids" { value = { for key, topic in google_pubsub_topic.dead_letter : key => topic.id } }
output "dead_letter_subscription_ids" { value = { for key, subscription in google_pubsub_subscription.dead_letter_audit : key => subscription.id } }
output "archive_contract" {
  value = {
    max_duration           = google_pubsub_subscription.raw_archive.cloud_storage_config[0].max_duration
    datetime_format        = google_pubsub_subscription.raw_archive.cloud_storage_config[0].filename_datetime_format
    use_topic_schema       = google_pubsub_subscription.raw_archive.cloud_storage_config[0].avro_config[0].use_topic_schema
    write_metadata         = google_pubsub_subscription.raw_archive.cloud_storage_config[0].avro_config[0].write_metadata
    dead_letter            = google_pubsub_subscription.raw_archive.dead_letter_policy[0].dead_letter_topic
    dead_letter_configured = length(google_pubsub_subscription.raw_archive.dead_letter_policy) == 1
  }
}
