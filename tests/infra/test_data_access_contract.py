import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
STACK_IAM = REPOSITORY_ROOT / "infra/stack/iam.tf"
STACK_IAM_DATAFLOW = REPOSITORY_ROOT / "infra/stack/iam_dataflow.tf"
STACK_IAM_STORAGE = REPOSITORY_ROOT / "infra/stack/iam_storage.tf"
STACK_LOCALS = REPOSITORY_ROOT / "infra/stack/locals.tf"
DATA_MODULE = REPOSITORY_ROOT / "infra/stack/modules/data/main.tf"
DATA_OUTPUTS = REPOSITORY_ROOT / "infra/stack/modules/data/outputs.tf"


def test_gold_views_use_authorized_datasets_without_mixed_iam_management() -> None:
    iam = STACK_IAM.read_text(encoding="utf-8")
    data = DATA_MODULE.read_text(encoding="utf-8")

    assert 'toset(["gold_internal", "ops", "silver"])' in data
    assert 'target_types = ["VIEWS"]' in data
    assert '!contains(["gold_internal", "ops", "silver"], binding.dataset)' in iam
    assert 'contains(["gold_internal", "ops", "silver"], binding.dataset)' in iam
    assert 'resource "google_bigquery_dataset_access" "runtime"' in iam


def test_release_files_store_ingestion_and_source_verification_separately() -> None:
    data = DATA_MODULE.read_text(encoding="utf-8")
    release_files_schema = data.split(
        'resource "google_bigquery_table" "release_files" {', maxsplit=1
    )[1].split("\n}", maxsplit=1)[0]

    assert '{ name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" }' in release_files_schema
    assert '{ name = "verified_at", type = "TIMESTAMP", mode = "REQUIRED" }' in release_files_schema


def test_datasets_clear_contents_only_after_protection_is_explicitly_disabled() -> None:
    data = DATA_MODULE.read_text(encoding="utf-8")

    assert "delete_contents_on_destroy  = !var.deletion_protection" in data


def test_dataflow_storage_roles_distinguish_metadata_read_list_and_writes() -> None:
    iam = "\n".join(
        (
            STACK_IAM.read_text(encoding="utf-8"),
            STACK_IAM_STORAGE.read_text(encoding="utf-8"),
        )
    )

    assert 'resource "google_storage_bucket_iam_member" "workflow_dataflow_bucket_reader"' in iam
    assert 'resource "google_storage_bucket_iam_member" "dataflow_bucket_reader"' in iam
    assert 'resource "google_storage_bucket_iam_member" "dataflow_bucket_viewer"' in iam
    assert 'role   = "roles/storage.bucketViewer"' in iam
    assert 'role   = "roles/storage.objectViewer"' in iam
    assert 'resource "google_storage_bucket_iam_member" "dataflow_temp_admin"' in iam


def test_dataflow_runtime_uses_minimal_custom_roles() -> None:
    locals_source = STACK_LOCALS.read_text(encoding="utf-8")
    iam = "\n".join(
        (
            STACK_IAM.read_text(encoding="utf-8"),
            STACK_IAM_DATAFLOW.read_text(encoding="utf-8"),
            STACK_IAM_STORAGE.read_text(encoding="utf-8"),
        )
    )
    dataflow_roles = locals_source.split("dataflow = toset([", maxsplit=1)[1].split(
        "])\n", maxsplit=1
    )[0]
    workflow_roles = locals_source.split("workflow = toset([", maxsplit=1)[1].split(
        "])\n", maxsplit=1
    )[0]

    assert '"roles/compute.viewer"' in dataflow_roles
    assert '"roles/viewer"' not in dataflow_roles
    assert '"roles/dataflow.worker"' not in dataflow_roles
    assert '"roles/dataflow.developer"' not in workflow_roles
    assert 'resource "google_project_iam_custom_role" "dataflow_runtime_worker"' in iam
    assert 'resource "google_project_iam_custom_role" "dataflow_bucket_metadata_reader"' in iam
    assert 'resource "google_project_iam_custom_role" "workflow_dataflow_operator"' in iam
    assert 'resource "google_project_iam_member" "dataflow_runtime_worker"' in iam
    assert 'resource "google_project_iam_member" "workflow_dataflow_operator"' in iam
    assert "role   = google_project_iam_custom_role.dataflow_bucket_metadata_reader.name" in iam
    assert 'member = local.runtime_members["dataflow"]' in iam


def test_predefined_dataflow_roles_are_never_granted_by_the_stack() -> None:
    terraform = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STACK_IAM.parent.glob("*.tf"))
    )

    grant = re.compile(r'role\s*=\s*"roles/dataflow\.(?:developer|worker)"')
    assert grant.search(terraform) is None


def test_dataflow_writes_only_the_two_streaming_tables() -> None:
    iam = STACK_IAM.read_text(encoding="utf-8")
    iam_dataflow = STACK_IAM_DATAFLOW.read_text(encoding="utf-8")
    locals_source = STACK_LOCALS.read_text(encoding="utf-8")
    outputs = DATA_OUTPUTS.read_text(encoding="utf-8")
    writer_role_marker = 'resource "google_project_iam_custom_role" "dataflow_table_writer" {'

    assert writer_role_marker in iam_dataflow

    writer_block = iam.split(
        'resource "google_bigquery_table_iam_member" "dataflow_stream_writer" {', maxsplit=1
    )[1].split("\n}", maxsplit=1)[0]
    writer_role_block = iam_dataflow.split(writer_role_marker, maxsplit=1)[1].split(
        "\n}", maxsplit=1
    )[0]

    assert '"dataflow:ops:roles/bigquery.dataEditor"' not in iam
    assert '"dataflow:silver:roles/bigquery.dataEditor"' not in iam
    assert '"dataflow:quarantine:roles/bigquery.dataEditor"' not in iam
    assert 'resource "google_bigquery_table_iam_member" "dataflow_stream_writer"' in iam
    assert "table_id   = module.data.streaming_table_ids.valid" in iam
    assert "table_id   = module.data.streaming_table_ids.quarantine" in iam
    assert "role       = local.dataflow_table_writer_role_name" in writer_block
    assert 'role       = "roles/bigquery.dataEditor"' not in writer_block
    assert "depends_on = [google_project_iam_custom_role.dataflow_table_writer]" in writer_block
    assert "role_id     = local.dataflow_table_writer_role_id" in writer_role_block
    assert 'dataflow_table_writer_role_id = "alfabetizacaoDataflowTableWriter"' in locals_source
    assert '"projects/${var.project_id}/roles/${local.dataflow_table_writer_role_id}"' in (
        locals_source
    )
    assert 'permissions = ["bigquery.tables.updateData"]' in writer_role_block
    assert all(
        permission not in writer_role_block
        for permission in (
            "bigquery.tables.delete",
            "bigquery.tables.export",
            "bigquery.tables.get",
            "bigquery.tables.getData",
            'bigquery.tables.update"',
        )
    )
    assert 'output "streaming_table_ids"' in outputs


def test_dataflow_reads_metadata_only_from_its_two_output_datasets() -> None:
    iam = STACK_IAM.read_text(encoding="utf-8")

    assert 'resource "google_project_iam_custom_role" "dataflow_dataset_metadata_reader"' in iam
    assert 'permissions = ["bigquery.datasets.get"]' in iam
    assert 'resource "google_bigquery_dataset_access" "dataflow_silver_metadata_reader"' in iam
    assert 'dataset_id    = module.data.dataset_ids["silver"]' in iam
    assert 'user_by_email = google_service_account.runtime["dataflow"].email' in iam
    quarantine_reader = re.search(
        r'resource "google_bigquery_dataset_iam_member"\s+"dataflow_quarantine_metadata_reader"',
        iam,
    )
    assert quarantine_reader is not None
    assert 'dataset_id = module.data.dataset_ids["quarantine"]' in iam
    assert (
        "role       = google_project_iam_custom_role.dataflow_dataset_metadata_reader.name" in iam
    )
    assert 'member     = local.runtime_members["dataflow"]' in iam


def test_dbt_can_materialize_staging_views_without_granting_staging_to_other_runtimes() -> None:
    iam = STACK_IAM.read_text(encoding="utf-8")
    staging_bindings = [
        " ".join(line.split()) for line in iam.splitlines() if 'dataset = "staging"' in line
    ]

    assert len(staging_bindings) == 1
    assert staging_bindings[0].startswith('"dbt:staging:roles/bigquery.dataEditor" =')
    assert 'account = "dbt", dataset = "staging"' in staging_bindings[0]
    assert 'role = "roles/bigquery.dataEditor"' in staging_bindings[0]


def test_workflow_can_only_list_stream_objects_and_act_as_dataflow() -> None:
    iam = STACK_IAM.read_text(encoding="utf-8")
    act_as_marker = 'resource "google_service_account_iam_member" "workflow_act_as" {'
    act_as_block = iam.split(act_as_marker, maxsplit=1)[1].split("\n}", maxsplit=1)[0]
    stream_observer_marker = (
        'resource "google_storage_bucket_iam_member" "workflow_stream_observer" {'
    )
    stream_observer_block = iam.split(stream_observer_marker, maxsplit=1)[1].split(
        "\n}", maxsplit=1
    )[0]
    subscription_marker = (
        'resource "google_pubsub_subscription_iam_member" "workflow_subscription_reader" {'
    )
    subscription_block = iam.split(subscription_marker, maxsplit=1)[1].split("\n}", maxsplit=1)[0]

    assert 'resource "google_project_iam_custom_role" "workflow_stream_lister"' in iam
    assert 'permissions = ["storage.objects.list"]' in iam
    assert "role   = google_project_iam_custom_role.workflow_stream_lister.name" in iam
    assert 'title       = "streaming_bucket_list"' in stream_observer_block
    bucket_condition = (
        "resource.name == 'projects/_/buckets/${module.storage.bucket_names.streaming}'"
    )
    assert bucket_condition in stream_observer_block
    assert "storage.objects.get" not in iam
    assert "archive  = module.streaming.archive_subscription_id" in subscription_block
    assert "dataflow = module.streaming.dataflow_subscription_id" in subscription_block
    assert "dead_letter_subscription_ids" not in subscription_block
    assert "role         = google_project_iam_custom_role.workflow_subscription_reader.name" in (
        subscription_block
    )
    assert 'member       = local.runtime_members["workflow"]' in subscription_block
    assert 'for_each = toset(["dataflow"])' in act_as_block
    assert all(account not in act_as_block for account in ('"batch"', '"dbt"', '"producer"'))
