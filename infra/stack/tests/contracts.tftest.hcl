mock_provider "google" {
  mock_data "google_project" {
    defaults = { number = "123456789012" }
  }
  mock_data "google_bigquery_dataset" {
    defaults = { location = "US" }
  }
}

mock_provider "google-beta" {
  mock_resource "google_project_service_identity" {
    defaults = {
      email = "service-123456789012@gcp-sa-pubsub.iam.gserviceaccount.com"
    }
  }
}

variables {
  project_id              = "fiap-fase2-test"
  billing_account_id      = "000000-000000-000000"
  data_location           = "US"
  storage_location        = "us-central1"
  region                  = "us-central1"
  name_prefix             = "fiap-fase2-test"
  artifacts_bucket_name   = "fiap-fase2-test-artifacts"
  batch_image             = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  dbt_image               = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/dbt@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  producer_image          = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/producer@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  dataflow_template_image = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow-template@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  dataflow_sdk_image      = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow-sdk@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  release_git_sha         = "0123456789abcdef0123456789abcdef01234567"
  reference_schema_uris = {
    uf                           = "gs://fiap-fase2-test-artifacts/reference/uf/schema.parquet"
    meta_alfabetizacao_brasil    = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_brasil/schema.parquet"
    meta_alfabetizacao_uf        = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_uf/schema.parquet"
    meta_alfabetizacao_municipio = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_municipio/schema.parquet"
    municipio                    = "gs://fiap-fase2-test-artifacts/reference/municipio/schema.parquet"
    alunos                       = "gs://fiap-fase2-test-artifacts/reference/alunos/schema.parquet"
  }
  budget_currency              = "BRL"
  runtime_entrypoints_verified = true
  stream_release_year          = 2024
  batch_reference_year         = 2032
  gold_consumer_principals     = ["group:dados@example.com"]
}

run "platform_contract" {
  command = plan

  assert {
    condition     = output.runtime_contract.scheduler.paused
    error_message = "O agendamento deve nascer pausado."
  }
  assert {
    condition     = output.runtime_contract.scheduler.schedule == "0 3 1 * *" && output.runtime_contract.scheduler.time_zone == "America/Sao_Paulo"
    error_message = "A agenda mensal deve respeitar o horário do challenge."
  }
  assert {
    condition     = output.runtime_contract.scheduler.reference_year == 2032
    error_message = "O Scheduler deve enviar o ano de referência configurado, nunca inferir o relógio."
  }
  assert {
    condition     = output.streaming_archive_contract.max_duration == "60s" && output.streaming_archive_contract.datetime_format == "YYYY/MM/DD/hh_mm_ssZ" && output.streaming_archive_contract.use_topic_schema && output.streaming_archive_contract.write_metadata && output.streaming_archive_contract.dead_letter_configured
    error_message = "A assinatura GCS deve gravar Avro do schema do tópico com metadados e rotação de 60 s."
  }
  assert {
    condition = (
      length(module.streaming.subscription_expiration_policy_ttls) == 4 &&
      alltrue([for ttl in module.streaming.subscription_expiration_policy_ttls : ttl == ""])
    )
    error_message = "As quatro assinaturas Pub/Sub devem permanecer sem expiração automática."
  }
  assert {
    condition     = module.streaming.schema_definition == file("${path.module}/../../schemas/events/MunicipalLiteracyRateUpdatedV1.avsc") && module.streaming.topic_encoding == "BINARY"
    error_message = "O tópico precisa publicar exatamente o contrato Avro canônico em codificação binária."
  }
  assert {
    condition = (
      toset(module.streaming.topic_persistence_regions) == toset(["us-central1"]) &&
      alltrue([
        for regions in values(module.streaming.dead_letter_persistence_regions) :
        toset(regions) == toset(["us-central1"])
      ])
    )
    error_message = "Tópicos principal e DLQ devem persistir mensagens somente em us-central1."
  }
  assert {
    condition = (
      output.streaming_table_contracts.valid == {
        ano                = "INTEGER"
        correlation_id     = "STRING"
        event_id           = "STRING"
        event_time         = "TIMESTAMP"
        id_municipio       = "STRING"
        ingestion_time     = "TIMESTAMP"
        message_id         = "STRING"
        publish_time       = "TIMESTAMP"
        rede               = "STRING"
        simulation         = "BOOLEAN"
        taxa_alfabetizacao = "NUMERIC"
        taxa_participacao  = "NUMERIC"
      } &&
      output.streaming_table_contracts.quarantine == {
        correlation_id    = "STRING"
        event_fingerprint = "STRING"
        ingestion_time    = "TIMESTAMP"
        message_id        = "STRING"
        reason_code       = "STRING"
      }
    )
    error_message = "Os schemas BigQuery devem aceitar exatamente as linhas válidas e de quarentena produzidas pelo Beam."
  }
  assert {
    condition     = output.external_table_contracts["alunos"].autodetect == false && startswith(output.external_table_contracts["alunos"].reference_file_schema_uri, "gs://") && output.external_table_contracts["alunos"].dataset_id == "bronze_restricted"
    error_message = "External Parquet deve usar arquivo de schema de referência e autodetect desligado."
  }
  assert {
    condition     = alltrue([for contract in values(output.external_table_contracts) : length(regexall("\\*", one(contract.source_uris))) == 1 && endswith(one(contract.source_uris), "/*")])
    error_message = "Cada external table deve usar exatamente um wildcard GCS suportado pelo BigQuery."
  }
  assert {
    condition = (
      can(yamldecode(output.stream_demo_workflow_contract)) &&
      yamldecode(output.stream_demo_workflow_contract)["main"].params == ["args"] &&
      contains(one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.init.assign if can(step.init)]), { correlation_id = "$${uuid.generate()}" }) &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.launch_flex if can(step.launch_flex)]).call == "googleapis.dataflow.v1b3.projects.locations.flexTemplates.launch" &&
      toset(keys(one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.launch_flex if can(step.launch_flex)]).args.body.launchParameter.parameters)) == toset(["input_subscription", "quarantine_table", "valid_table"]) &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.launch_flex if can(step.launch_flex)]).args.body.launchParameter.environment.additionalUserLabels.run_id == "$${correlation_id}" &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.publish_fixture if can(step.publish_fixture)]).args.body.overrides.containerOverrides == [{
        args = ["--mode", "pubsub", "--topic", "$${topic}", "--fixture", "/app/contracts/events/fixtures/demo.json", "--report", "/tmp/producer-report.json", "--year", "$${string(release_year)}"]
        env  = [{ name = "CORRELATION_ID", value = "$${correlation_id}" }]
      }] &&
      one(flatten([for branch in one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.independent_stage_checks.parallel.branches if can(step.independent_stage_checks)]) : [for step in try(branch.staging_branch.steps, []) : step.wait_silver if can(step.wait_silver)]])).args == {
        project_id           = "$${project_id}"
        query                = "$${silver_query}"
        expected             = 8
        correlation_id       = "$${correlation_id}"
        window_start         = "$${window_start}"
        maximum_bytes_billed = "$${maximum_bytes_billed}"
        data_location        = "$${data_location}"
        max_attempts         = 60
      } &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.request_drain if can(step.request_drain)]).call == "googleapis.dataflow.v1b3.projects.locations.jobs.update" &&
      one(flatten([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : [for cleanup_step in try(step.guarded_execution["except"].steps, []) : cleanup_step.cleanup_after_failure["try"] if can(cleanup_step.cleanup_after_failure)]])).call == "cleanup_dataflow"
    )
    error_message = "O demo deve correlacionar arquivo e oito eventos Silver da execução atual, sem espera fixa."
  }
  assert {
    condition = (
      toset(keys(yamldecode(output.stream_demo_workflow_contract))) == toset(["cleanup_dataflow", "main", "wait_bigquery_count", "wait_dataflow_state", "wait_gcs_object", "wait_main_subscription_backlogs", "wait_no_dead_letter_events"]) &&
      yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.params == ["project_id", "region", "job_id", "job_name", "correlation_id"] &&
      contains(one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.init_page_scan.assign if can(step.init_page_scan)]), { visited_page_tokens = [""] }) &&
      contains(one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.init_page_scan.assign if can(step.init_page_scan)]), { duplicate_match = false }) &&
      one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.list_active_jobs if can(step.list_active_jobs)]).args == {
        projectId        = "$${project_id}"
        location         = "$${region}"
        filter           = "ACTIVE"
        pageSize         = 100
        pageToken        = "$${page_token}"
        connector_params = { timeout = 30 }
      } &&
      contains(one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.guard_next_page.switch if can(step.guard_next_page)]), { condition = "$${next_page_token in visited_page_tokens}", next = "no_matching_job" }) &&
      contains(one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.choose_unique_match.switch if can(step.choose_unique_match)]), { condition = "$${duplicate_match}", next = "no_matching_job" }) &&
      one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.inspect_known if can(step.inspect_known)]).call == "googleapis.dataflow.v1b3.projects.locations.jobs.get" &&
      one([for step in yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow.steps : step.cancel if can(step.cancel)]).call == "googleapis.dataflow.v1b3.projects.locations.jobs.update" &&
      alltrue(flatten([
        for function in [yamldecode(output.stream_demo_workflow_contract).cleanup_dataflow, yamldecode(output.stream_demo_workflow_contract).wait_dataflow_state, yamldecode(output.stream_demo_workflow_contract).wait_bigquery_count, yamldecode(output.stream_demo_workflow_contract).wait_gcs_object, yamldecode(output.stream_demo_workflow_contract).wait_main_subscription_backlogs] : [
          for step in function.steps : !can(step.args.seconds) || step.args.seconds == 10
        ]
      ]))
    )
    error_message = "O source_contents implantado deve proteger o launch e recuperar um único job mesmo com paginação, ciclos e resultado ambíguo."
  }
  assert {
    condition = (
      endswith(output.release_data_contract.files_table, ".ops.release_files") &&
      endswith(output.release_data_contract.registry_table, ".ops.release_registry") &&
      endswith(output.release_data_contract.results_table, ".quality.release_results") &&
      contains(keys(output.resource_inventory.datasets), "staging") &&
      contains(keys(output.resource_inventory.datasets), "quality") &&
      contains(keys(output.resource_inventory.datasets), "gold_internal")
    )
    error_message = "O stack deve materializar o contrato canônico de release e seus datasets dbt."
  }
  assert {
    condition = (
      toset(output.gold_authorized_views_contract.source_datasets) == toset(["gold_internal", "ops", "silver"]) &&
      output.gold_authorized_views_contract.view_dataset == "gold" &&
      toset(output.gold_authorized_views_contract.target_types) == toset(["VIEWS"])
    )
    error_message = "Gold público deve acessar Gold interno por authorized dataset restrito a views."
  }
  assert {
    condition     = google_billing_budget.pipeline[0].amount[0].specified_amount[0].currency_code == "BRL" && google_billing_budget.pipeline[0].amount[0].specified_amount[0].units == "50"
    error_message = "O default de 50 só deve ser aplicado quando BRL foi escolhido."
  }
  assert {
    condition     = output.budget_contract.amount == 50 && output.budget_contract.currency == "BRL" && output.budget_contract.hard_cap == false
    error_message = "Budget deve ser apenas alerta, nunca corte automático."
  }
  assert {
    condition     = output.runtime_contract.permanent_job_count == 0 && output.runtime_contract.dataflow_min_workers == 1 && output.runtime_contract.dataflow_max_workers == 2
    error_message = "Terraform não pode iniciar job Dataflow permanente."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.workflow_operation_reader.permissions) == toset(["run.operations.get"]) &&
      google_project_iam_custom_role.workflow_operation_reader.role_id == "alfabetizacaoWorkflowOperationReader" &&
      google_project_iam_member.workflow_operation_reader.project == var.project_id
    )
    error_message = "O Workflow precisa consultar somente a operação assíncrona iniciada pelo Cloud Run Job."
  }
  assert {
    condition = (
      output.flex_template_contract.supports_streaming &&
      output.flex_template_contract.parameter_help_texts == {
        input_subscription = "Assinatura Pub/Sub consumida pelo pipeline."
        quarantine_table   = "Tabela BigQuery que recebe eventos rejeitados."
        valid_table        = "Tabela BigQuery que recebe eventos válidos."
      }
    )
    error_message = "O ContainerSpec deve declarar streaming e documentar todos os parâmetros obrigatórios."
  }
  assert {
    condition     = output.lifecycle_contracts["landing"][0].age == 7 && length(output.lifecycle_contracts["bronze"]) == 0 && length(output.lifecycle_contracts["streaming"]) == 2
    error_message = "Landing deve expirar em 7d, Bronze preserva histórico e streaming/quarentena expiram em 30d."
  }
  assert {
    condition = (
      alltrue([
        for key in ["landing", "streaming", "dataflow"] :
        !output.storage_retention_contracts[key].versioning_enabled &&
        output.storage_retention_contracts[key].soft_delete_seconds == 0
      ]) &&
      alltrue([
        for key in ["bronze", "control"] :
        output.storage_retention_contracts[key].versioning_enabled &&
        output.storage_retention_contracts[key].soft_delete_seconds == null
      ])
    )
    error_message = "Buckets efêmeros não devem preservar objetos excluídos; Bronze e control mantêm as proteções."
  }
  assert {
    condition     = output.security_contract.basic_owner_or_editor_grants == [] && output.security_contract.restricted_student_dataset == "silver_restricted" && output.security_contract.bronze_student_dataset == "bronze_restricted" && output.security_contract.bronze_batch_can_delete == false && output.security_contract.deletion_protection
    error_message = "O contrato negativo deve impedir papéis básicos, PII fora do restrito e deletes Bronze."
  }
  assert {
    condition     = !anytrue(values(module.data.dataset_delete_contents_on_destroy))
    error_message = "Datasets devem manter o conteúdo protegido enquanto deletion_protection estiver habilitada."
  }
  assert {
    condition = (
      google_bigquery_dataset_iam_member.gold_consumer["group:dados@example.com"].role == "roles/bigquery.dataViewer" &&
      google_project_iam_member.gold_consumer_job_user["group:dados@example.com"].role == "roles/bigquery.jobUser" &&
      toset(output.security_contract.gold_consumer_principals) == toset(["group:dados@example.com"])
    )
    error_message = "Consumidores declarados devem consultar Gold sem acesso aos datasets candidatos."
  }
  assert {
    condition     = google_storage_bucket_iam_member.batch_bronze_creator.role == "roles/storage.objectCreator" && google_storage_bucket_iam_member.batch_bronze_viewer.role == "roles/storage.objectViewer" && alltrue([for binding in values(local.dataset_bindings) : binding.account != "batch" || !contains(["bronze_restricted", "silver_restricted"], binding.dataset)])
    error_message = "Batch não pode deletar Bronze nem ler datasets restritos de alunos."
  }
  assert {
    condition = (
      length([for binding in values(local.dataset_bindings) : binding if binding.account == "dataflow"]) == 0 &&
      toset(keys(google_bigquery_table_iam_member.dataflow_stream_writer)) == toset(["quarantine", "valid"]) &&
      google_project_iam_custom_role.dataflow_table_writer.role_id == local.dataflow_table_writer_role_id &&
      local.dataflow_table_writer_role_id == "alfabetizacaoDataflowTableWriter" &&
      local.dataflow_table_writer_role_name == "projects/${var.project_id}/roles/alfabetizacaoDataflowTableWriter" &&
      toset(google_project_iam_custom_role.dataflow_table_writer.permissions) == toset(["bigquery.tables.updateData"]) &&
      alltrue([for binding in values(google_bigquery_table_iam_member.dataflow_stream_writer) : binding.role == local.dataflow_table_writer_role_name]) &&
      google_bigquery_table_iam_member.dataflow_stream_writer["valid"].dataset_id == module.data.dataset_ids["silver"] &&
      google_bigquery_table_iam_member.dataflow_stream_writer["valid"].table_id == module.data.streaming_table_ids.valid &&
      google_bigquery_table_iam_member.dataflow_stream_writer["quarantine"].dataset_id == module.data.dataset_ids["quarantine"] &&
      google_bigquery_table_iam_member.dataflow_stream_writer["quarantine"].table_id == module.data.streaming_table_ids.quarantine
    )
    error_message = "Dataflow só pode inserir dados nas duas tabelas do streaming por papel custom com bigquery.tables.updateData."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.dataflow_dataset_metadata_reader.permissions) == toset(["bigquery.datasets.get"]) &&
      google_project_iam_custom_role.dataflow_dataset_metadata_reader.role_id == "alfabetizacaoDataflowDatasetMetadataReader" &&
      google_bigquery_dataset_access.dataflow_silver_metadata_reader.dataset_id == module.data.dataset_ids["silver"] &&
      google_bigquery_dataset_iam_member.dataflow_quarantine_metadata_reader.dataset_id == module.data.dataset_ids["quarantine"]
    )
    error_message = "Dataflow deve ler somente metadados dos dois datasets de saída, sem ganhar leitura de dados ou escrita no dataset."
  }
  assert {
    condition = (
      local.dataset_bindings["dbt:staging:roles/bigquery.dataEditor"].account == "dbt" &&
      local.dataset_bindings["dbt:staging:roles/bigquery.dataEditor"].dataset == "staging" &&
      local.dataset_bindings["dbt:staging:roles/bigquery.dataEditor"].role == "roles/bigquery.dataEditor" &&
      length([for binding in values(local.dataset_bindings) : binding if binding.dataset == "staging"]) == 1
    )
    error_message = "Somente dbt-sa deve materializar as views do dataset staging."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.workflow_stream_lister.permissions) == toset(["storage.objects.list"]) &&
      google_project_iam_custom_role.workflow_stream_lister.role_id == "alfabetizacaoWorkflowStreamLister"
    )
    error_message = "O Workflow deve apenas listar nomes no bucket de streaming, sem ler payloads."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.workflow_subscription_reader.permissions) == toset(["pubsub.subscriptions.get"]) &&
      google_project_iam_custom_role.workflow_subscription_reader.role_id == "alfabetizacaoWorkflowSubscriptionReader" &&
      toset(keys(google_pubsub_subscription_iam_member.workflow_subscription_reader)) == toset(["archive", "dataflow"])
    )
    error_message = "O Workflow só pode consultar as duas subscriptions principais pela permissão mínima de get."
  }
  assert {
    condition     = toset(keys(google_service_account_iam_member.workflow_act_as)) == toset(["dataflow"])
    error_message = "O Workflow só pode anexar a conta Dataflow; jobs Cloud Run preservam suas identidades configuradas."
  }
  assert {
    condition = (
      !contains(local.project_roles.workflow, "roles/run.jobsExecutorWithOverrides") &&
      toset(keys(google_cloud_run_v2_job_iam_member.workflow_job_executor)) == toset(["batch", "dbt", "producer"])
    )
    error_message = "O executor do Workflow deve existir somente nos três Jobs Cloud Run que ele invoca."
  }
  assert {
    condition = (
      contains(local.project_roles.dataflow, "roles/compute.viewer") &&
      !contains(local.project_roles.dataflow, "roles/viewer") &&
      !contains(local.project_roles.dataflow, "roles/dataflow.worker") &&
      !contains(local.project_roles.workflow, "roles/dataflow.developer") &&
      contains(keys(google_project_iam_member.runtime), "dataflow:roles/compute.viewer")
    )
    error_message = "A conta Dataflow deve inspecionar recursos Compute sem receber Viewer nem papéis Dataflow predefinidos."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.dataflow_runtime_worker.permissions) == toset([
        "autoscaling.sites.readRecommendations",
        "autoscaling.sites.writeMetrics",
        "autoscaling.sites.writeState",
        "compute.instanceGroupManagers.update",
        "compute.instances.delete",
        "compute.instances.setDiskAutoDelete",
        "dataflow.jobs.get",
        "dataflow.shuffle.read",
        "dataflow.shuffle.write",
        "dataflow.streamingWorkItems.ImportState",
        "dataflow.streamingWorkItems.commitWork",
        "dataflow.streamingWorkItems.getData",
        "dataflow.streamingWorkItems.getWork",
        "dataflow.streamingWorkItems.getWorkerMetadata",
        "dataflow.workItems.lease",
        "dataflow.workItems.sendMessage",
        "dataflow.workItems.update",
      ]) &&
      google_project_iam_custom_role.dataflow_runtime_worker.role_id == "alfabetizacaoDataflowRuntimeWorker" &&
      google_project_iam_member.dataflow_runtime_worker.project == var.project_id &&
      toset(google_project_iam_custom_role.dataflow_bucket_metadata_reader.permissions) == toset(["storage.buckets.get"]) &&
      google_project_iam_custom_role.dataflow_bucket_metadata_reader.role_id == "alfabetizacaoDataflowBucketMetadataReader" &&
      google_storage_bucket_iam_member.dataflow_bucket_reader.bucket == module.storage.bucket_names["dataflow"]
    )
    error_message = "O worker deve receber somente as permissões operacionais do streaming; storage, logs e métricas ficam nos bindings específicos."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.workflow_dataflow_operator.permissions) == toset([
        "dataflow.jobs.cancel",
        "dataflow.jobs.create",
        "dataflow.jobs.get",
        "dataflow.jobs.list",
        "resourcemanager.projects.get",
      ]) &&
      google_project_iam_custom_role.workflow_dataflow_operator.role_id == "alfabetizacaoWorkflowDataflowOperator" &&
      google_project_iam_member.workflow_dataflow_operator.project == var.project_id
    )
    error_message = "O Workflow deve receber somente as operações Dataflow necessárias à demonstração."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.workflow_log_writer.permissions) == toset(["logging.logEntries.create"]) &&
      google_project_iam_custom_role.workflow_log_writer.role_id == local.workflow_log_writer_role_id &&
      local.workflow_log_writer_role_name == "projects/${var.project_id}/roles/alfabetizacaoWorkflowLogWriter" &&
      google_project_iam_member.workflow_log_writer.role == local.workflow_log_writer_role_name &&
      google_project_iam_member.workflow_log_writer.project == var.project_id &&
      !contains(local.project_roles.workflow, "roles/logging.logWriter")
    )
    error_message = "O Workflow só pode escrever a entrada de log usada pelo fallback de limpeza."
  }
  assert {
    condition = (
      contains(local.project_roles.workflow, "roles/bigquery.jobUser") &&
      alltrue([
        for dataset in ["gold", "ops", "quarantine", "silver"] :
        local.dataset_bindings["workflow:${dataset}:roles/bigquery.dataViewer"].role == "roles/bigquery.dataViewer"
      ]) &&
      !contains(local.project_roles.workflow, "roles/bigquery.dataViewer")
    )
    error_message = "O Workflow deve consultar somente os quatro datasets da demo, sem dataViewer no projeto."
  }
  assert {
    condition = (
      length(module.runtime.stream_demo_environment) == 18 &&
      module.runtime.stream_demo_environment["ALFABETIZACAO_DATAFLOW_SDK_CONTAINER_IMAGE"] == var.dataflow_sdk_image &&
      module.runtime.stream_demo_environment["ALFABETIZACAO_VALID_TABLE"] == "${var.project_id}:silver.municipal_rate_stream" &&
      module.runtime.stream_demo_environment["ALFABETIZACAO_QUARANTINE_TABLE"] == "${var.project_id}:quarantine.stream_events" &&
      module.runtime.stream_demo_environment["ALFABETIZACAO_GOLD_TABLE"] == "${var.project_id}.gold.indicador_atual_hibrido" &&
      module.runtime.stream_demo_environment["ALFABETIZACAO_MAXIMUM_BYTES_BILLED"] == tostring(var.maximum_bytes_billed)
    )
    error_message = "O workflow deve receber as 18 constantes imutáveis sem exceder o limite da plataforma."
  }
  assert {
    condition = (
      output.flex_template_contract.container_image == var.dataflow_template_image &&
      output.flex_template_contract.container_image != module.runtime.stream_demo_environment["ALFABETIZACAO_DATAFLOW_SDK_CONTAINER_IMAGE"]
    )
    error_message = "O ContainerSpec Flex deve usar o launcher e o Workflow deve usar uma imagem SDK distinta."
  }
  assert {
    condition     = output.runtime_contract.maximum_bytes_billed == 26843545600 && alltrue([for job in values(output.runtime_contract.jobs) : job.task_count == 1 && can(regex("@sha256:[0-9a-f]{64}$", job.image))])
    error_message = "Jobs devem ser efêmeros, unitários, por digest e carregar o cap de 25 GiB."
  }
  assert {
    condition     = output.runtime_entrypoint_contract.status == "verified-by-integration" && output.runtime_entrypoint_contract.requires_integration_gate
    error_message = "Entrypoints de Batch e Producer só podem ser liberados após o gate da integração."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["batch"].command == tolist(["alfabetizacao"]) &&
      output.runtime_entrypoint_contract.jobs["batch"].args == tolist(["batch", "run", "--source", "municipio", "--year", "2024", "--dry-run", "--format", "json"]) &&
      output.runtime_entrypoint_contract.jobs["dbt"].args == tolist(["build", "--target", "cloud", "--project-dir", "dbt", "--profiles-dir", "dbt"]) &&
      output.runtime_entrypoint_contract.jobs["producer"].command == tolist(["python", "-m", "alfabetizacao_pipeline.streaming.producer"]) &&
      output.runtime_entrypoint_contract.jobs["producer"].args[0] == "--mode" &&
      contains(output.runtime_entrypoint_contract.jobs["producer"].args, "--year") &&
      contains(output.runtime_entrypoint_contract.jobs["producer"].args, "2024")
    )
    error_message = "Os jobs devem expor os entrypoints reais validados no SHA integrado."
  }
  assert {
    condition = (
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.build_stream_models if can(step.build_stream_models)]).call == "googleapis.run.v2.projects.locations.jobs.run" &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.build_stream_models if can(step.build_stream_models)]).args.body.overrides.containerOverrides == [{
        args = ["build", "--target", "cloud", "--project-dir", "dbt", "--profiles-dir", "dbt", "--select", "tag:stream_demo"]
        env  = [{ name = "CORRELATION_ID", value = "$${correlation_id}" }, { name = "RUN_STARTED", value = "$${window_start}" }]
      }] &&
      one([for step in one([for step in yamldecode(output.stream_demo_workflow_contract)["main"].steps : step.guarded_execution["try"].steps if can(step.guarded_execution)]) : step.build_stream_models if can(step.build_stream_models)]).args.connector_params.timeout == 3900
    )
    error_message = "O override dbt do demo deve preservar target e diretórios reais da imagem."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_GCP_PROJECT_ID"] == "fiap-fase2-test" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_MAX_BYTES_BILLED"] == "26843545600" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_GIT_SHA"] == "0123456789abcdef0123456789abcdef01234567" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_IMAGE_DIGEST"] == "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_LANDING_PREFIX"] == "gs://fiap-fase2-test-fiap-fase2-test-landing/landing/batch" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_BRONZE_PREFIX"] == "gs://fiap-fase2-test-fiap-fase2-test-bronze/bronze" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_MANIFEST_PREFIX"] == "gs://fiap-fase2-test-fiap-fase2-test-control/manifests"
    )
    error_message = "O job Batch deve receber o ambiente prefixado lido por AppSettings."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["dbt"].env["DBT_MAXIMUM_BYTES_BILLED"] == "26843545600" &&
      output.runtime_entrypoint_contract.jobs["dbt"].env["DBT_LOCATION"] == "US" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_BIGQUERY_LOCATION"] == "US" &&
      output.runtime_contract.data_location == "US" &&
      output.runtime_contract.storage_location == "us-central1" &&
      output.runtime_contract.compute_region == "us-central1"
    )
    error_message = "O dbt deve receber localização e teto de bytes configuráveis no profile cloud."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["dbt"].env["GCP_PROJECT_ID"] == "fiap-fase2-test" &&
      output.runtime_entrypoint_contract.jobs["dbt"].env["DBT_LOCATION"] == "US"
    )
    error_message = "O job dbt deve receber projeto e localização descobertos pelo stack."
  }
  assert {
    condition = (
      strcontains(output.batch_workflow_contract, "containerOverrides") &&
      strcontains(output.batch_workflow_contract, "--execute") &&
      strcontains(output.batch_workflow_contract, "$${map.get(input, \"year\")}") &&
      strcontains(output.batch_workflow_contract, "year == null or year < 2000 or year > 2100") &&
      !strcontains(output.batch_workflow_contract, "input.sources") &&
      strcontains(output.batch_workflow_contract, "release, begin") &&
      strcontains(output.batch_workflow_contract, "release, complete") &&
      strcontains(output.batch_workflow_contract, "release, fail") &&
      strcontains(output.batch_workflow_contract, "release_nonce") &&
      strcontains(output.batch_workflow_contract, "unsupported action") &&
      strcontains(output.batch_workflow_contract, "cleanup_error") &&
      strcontains(output.batch_workflow_contract, "connector_params") &&
      !strcontains(output.batch_workflow_contract, "projects.locations.operations.get") &&
      alltrue([for source in ["uf", "meta_alfabetizacao_brasil", "meta_alfabetizacao_uf", "meta_alfabetizacao_municipio", "municipio", "alunos"] : strcontains(output.batch_workflow_contract, source)])
    )
    error_message = "O Workflow mensal deve executar as seis fontes com fonte, ano e modo explícitos."
  }
  assert {
    condition = (
      output.flex_template_contract.has_sdk_info &&
      !output.flex_template_contract.has_legacy_sdk_key &&
      can(regex("^templates/municipal-literacy-rate/[0-9a-f]{64}\\.json$", output.flex_template_contract.object_name)) &&
      output.flex_template_contract.uri == module.runtime.stream_demo_environment["ALFABETIZACAO_FLEX_TEMPLATE_URI"] &&
      output.flex_template_contract.content_sha256 == regex("/([0-9a-f]{64})\\.json$", output.flex_template_contract.uri)[0] &&
      !strcontains(output.flex_template_contract.uri, "flex-template.json")
    )
    error_message = "O ContainerSpec Flex deve ser canônico, content-addressed e consumido diretamente pelo Workflow."
  }
  assert {
    condition = (
      strcontains(google_monitoring_alert_policy.log_failure["batch_failure"].conditions[0].condition_threshold[0].filter, "resource.type=\"cloud_run_job\"") &&
      !strcontains(google_monitoring_alert_policy.log_failure["batch_failure"].conditions[0].condition_threshold[0].filter, "resource.type=\"global\"") &&
      strcontains(google_monitoring_alert_policy.dataflow_failure.conditions[0].condition_threshold[0].filter, "resource.type=\"dataflow_job\"") &&
      strcontains(google_monitoring_alert_policy.dataflow_failure.conditions[0].condition_threshold[0].filter, "dataflow.googleapis.com/job/is_failed")
    )
    error_message = "Alertas de métricas baseadas em logs devem consultar o monitored resource que originou cada série."
  }
  assert {
    condition = (
      google_logging_metric.pipeline["batch_processed_rows"].value_extractor == "EXTRACT(jsonPayload.row_count)" &&
      strcontains(google_logging_metric.pipeline["batch_processed_rows"].filter, "jsonPayload.status=\"completed\"") &&
      strcontains(google_logging_metric.pipeline["data_quality_critical"].filter, "failure|error) in test") &&
      strcontains(google_logging_metric.pipeline["quality_quarantine"].filter, "textPayload=~") &&
      strcontains(google_logging_metric.pipeline["quality_duplicate"].filter, "textPayload=~")
    )
    error_message = "Volume, reprovações dbt e execução dos modelos de qualidade devem derivar de stdout/stderr realmente emitidos."
  }
  assert {
    condition = alltrue(concat(
      [for policy in google_monitoring_alert_policy.log_failure : !strcontains(policy.conditions[0].condition_threshold[0].filter, "custom.googleapis.com")],
      [for policy in google_monitoring_alert_policy.pubsub_backlog : !strcontains(policy.conditions[0].condition_threshold[0].filter, "custom.googleapis.com")],
      [
        !strcontains(google_monitoring_alert_policy.dataflow_failure.conditions[0].condition_threshold[0].filter, "custom.googleapis.com"),
        !strcontains(google_monitoring_alert_policy.stream_latency.conditions[0].condition_threshold[0].filter, "custom.googleapis.com"),
        !strcontains(google_monitoring_dashboard.pipeline.dashboard_json, "custom.googleapis.com"),
      ],
    ))
    error_message = "A infraestrutura não deve declarar métricas customizadas sem um emissor executável."
  }
  assert {
    condition = (
      strcontains(google_monitoring_alert_policy.stream_latency.conditions[0].condition_threshold[0].filter, "pubsub.googleapis.com/subscription/oldest_unacked_message_age") &&
      google_monitoring_alert_policy.stream_latency.conditions[0].condition_threshold[0].comparison == "COMPARISON_GT" &&
      google_monitoring_alert_policy.stream_latency.conditions[0].condition_threshold[0].threshold_value == 59 &&
      length(google_monitoring_alert_policy.pubsub_backlog) == 4
    )
    error_message = "Latência e backlog devem usar métricas nativas e cobrir assinaturas principais e DLQs."
  }
  assert {
    condition = alltrue([
      for signal in [
        "ack_message_count",
        "oldest_unacked_message_age",
        "batch_processed_rows",
        "quality_quarantine",
        "quality_duplicate",
      ] : strcontains(google_monitoring_dashboard.pipeline.dashboard_json, signal)
    ])
    error_message = "O dashboard deve expor volume/freshness, latência, quarentena e duplicatas sem métricas fictícias."
  }
}

run "teardown_requires_explicit_protection_change" {
  command = plan
  variables { deletion_protection = false }
  assert {
    condition = (
      output.runtime_contract.jobs["batch"].deletion_protection == false &&
      output.security_contract.deletion_protection == false &&
      alltrue(values(output.runtime_contract.storage_force_destroy)) &&
      alltrue(values(module.data.dataset_delete_contents_on_destroy))
    )
    error_message = "O apply preparatório deve remover as proteções gerenciadas e permitir a remoção dos datasets antes do destroy."
  }
}

run "scheduler_can_be_enabled_explicitly" {
  command = plan
  variables { scheduler_enabled = true }
  assert {
    condition     = output.runtime_contract.scheduler.paused == false
    error_message = "Somente a variável explícita pode habilitar a agenda."
  }
}

run "rejects_scheduler_without_reference_year" {
  command = plan
  variables {
    scheduler_enabled    = true
    batch_reference_year = null
  }
  expect_failures = [var.scheduler_enabled]
}

run "rejects_non_brl_implicit_budget" {
  command = plan
  variables {
    budget_currency = "USD"
    budget_amount   = null
  }
  expect_failures = [check.budget_contract]
}

run "rejects_invalid_or_conflated_images" {
  command = plan
  variables {
    batch_image        = "us-docker.pkg.dev/fiap-fase2-test/pipeline/batch:latest"
    dataflow_sdk_image = "us-central1-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow-template@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  }
  expect_failures = [var.batch_image, var.dataflow_sdk_image]
}

run "rejects_fractional_maximum_bytes_billed" {
  command = plan
  variables { maximum_bytes_billed = 1024.5 }
  expect_failures = [var.maximum_bytes_billed]
}

run "rejects_malformed_project_and_billing" {
  command = plan
  variables {
    project_id         = "Projeto Inválido!"
    billing_account_id = "billing-invalido"
  }
  expect_failures = [var.project_id, var.billing_account_id]
}

run "rejects_unverified_runtime_entrypoints" {
  command = plan
  variables { runtime_entrypoints_verified = false }
  expect_failures = [output.runtime_entrypoint_contract]
}

run "rejects_cross_region_storage_or_compute" {
  command = plan
  variables {
    storage_location = "southamerica-east1"
  }
  expect_failures = [check.storage_location_is_compatible_with_bigquery]
}

run "rejects_alternate_us_storage_region" {
  command = plan
  variables {
    storage_location        = "us-east1"
    region                  = "us-east1"
    batch_image             = "us-east1-docker.pkg.dev/fiap-fase2-test/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    dbt_image               = "us-east1-docker.pkg.dev/fiap-fase2-test/pipeline/dbt@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    producer_image          = "us-east1-docker.pkg.dev/fiap-fase2-test/pipeline/producer@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    dataflow_template_image = "us-east1-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow-template@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
    dataflow_sdk_image      = "us-east1-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow-sdk@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  }
  expect_failures = [check.storage_location_is_compatible_with_bigquery]
}

run "rejects_image_from_external_registry_project" {
  command = plan
  variables {
    batch_image = "us-central1-docker.pkg.dev/outro-projeto/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.batch_image]
}

run "rejects_reference_schema_outside_bootstrap_bucket" {
  command = plan
  variables {
    reference_schema_uris = {
      uf                           = "gs://outro-bucket/reference/uf/schema.parquet"
      meta_alfabetizacao_brasil    = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_brasil/schema.parquet"
      meta_alfabetizacao_uf        = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_uf/schema.parquet"
      meta_alfabetizacao_municipio = "gs://fiap-fase2-test-artifacts/reference/meta_alfabetizacao_municipio/schema.parquet"
      municipio                    = "gs://fiap-fase2-test-artifacts/reference/municipio/schema.parquet"
      alunos                       = "gs://fiap-fase2-test-artifacts/reference/alunos/schema.parquet"
    }
  }
  expect_failures = [var.reference_schema_uris]
}
