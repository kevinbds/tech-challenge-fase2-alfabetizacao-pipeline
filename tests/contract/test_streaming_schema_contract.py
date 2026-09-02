import re
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

REPOSITORY_ROOT = Path(__file__).parents[2]
CANONICAL_SCHEMA = REPOSITORY_ROOT / "schemas/events/MunicipalLiteracyRateUpdatedV1.avsc"
STACK_STREAMING = REPOSITORY_ROOT / "infra/stack/streaming.tf"
STACK_IAM = REPOSITORY_ROOT / "infra/stack/iam.tf"
STREAMING_MODULE = REPOSITORY_ROOT / "infra/stack/modules/streaming/main.tf"
JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


def test_terraform_provisions_the_canonical_binary_avro_contract() -> None:
    root_configuration = STACK_STREAMING.read_text(encoding="utf-8")
    module_configuration = STREAMING_MODULE.read_text(encoding="utf-8")
    file_call = re.search(
        r'municipal_rate_schema_definition\s*=\s*file\("\$\{path\.module\}/([^\"]+)"\)',
        root_configuration,
    )

    assert file_call is not None
    provisioned_schema = JSON_MAPPING.validate_json(
        (STACK_STREAMING.parent / file_call.group(1)).resolve().read_text(encoding="utf-8")
    )
    canonical_schema = JSON_MAPPING.validate_json(CANONICAL_SCHEMA.read_text(encoding="utf-8"))

    assert provisioned_schema == canonical_schema
    assert "definition = var.municipal_rate_schema_definition" in module_configuration
    assert 'encoding = "BINARY"' in module_configuration


def test_archive_subscription_waits_for_its_custom_service_account_grants() -> None:
    root_configuration = STACK_STREAMING.read_text(encoding="utf-8")

    for dependency in (
        "google_project_iam_member.pubsub_service_agent",
        "google_storage_bucket_iam_member.archive_creator",
        "google_storage_bucket_iam_member.archive_bucket_reader",
        "google_service_account_iam_member.pubsub_archive_token_creator",
    ):
        assert dependency in root_configuration


def test_pubsub_service_agent_is_materialized_before_iam_is_granted() -> None:
    iam_configuration = STACK_IAM.read_text(encoding="utf-8")

    assert 'resource "google_project_service_identity" "pubsub"' in iam_configuration
    assert '"pubsub.googleapis.com"' in iam_configuration
    assert "google_project_service_identity.pubsub.email" in iam_configuration
    assert 'role    = "roles/pubsub.serviceAgent"' in iam_configuration
