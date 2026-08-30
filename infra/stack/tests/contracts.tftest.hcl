mock_provider "google" {
  mock_data "google_project" {
    defaults = { number = "123456789012" }
  }
}

variables {
  project_id            = "fiap-fase2-test"
  billing_account_id    = "000000-000000-000000"
  data_location         = "southamerica-east1"
  region                = "southamerica-east1"
  name_prefix           = "fiap-fase2-test"
  artifacts_bucket_name = "fiap-fase2-test-artifacts"
  batch_image           = "us-docker.pkg.dev/fiap-fase2-test/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  dbt_image             = "us-docker.pkg.dev/fiap-fase2-test/pipeline/dbt@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  producer_image        = "us-docker.pkg.dev/fiap-fase2-test/pipeline/producer@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  dataflow_image        = "us-docker.pkg.dev/fiap-fase2-test/pipeline/dataflow@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  release_git_sha       = "0123456789abcdef0123456789abcdef01234567"
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
    condition     = output.streaming_archive_contract.max_duration == "60s" && output.streaming_archive_contract.datetime_format == "year=YYYY/month=MM/day=DD/hour=hh/mm_ssZ" && output.streaming_archive_contract.use_topic_schema && output.streaming_archive_contract.write_metadata && output.streaming_archive_contract.dead_letter_configured
    error_message = "A assinatura GCS deve gravar Avro do schema do tópico com metadados e rotação de 60 s."
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
        ingestion_time = "TIMESTAMP"
        message_id     = "STRING"
        reason_code    = "STRING"
      }
    )
    error_message = "Os schemas BigQuery devem aceitar exatamente as linhas válidas e de quarentena produzidas pelo Beam."
  }
  assert {
    condition     = output.external_table_contracts["alunos"].autodetect == false && startswith(output.external_table_contracts["alunos"].reference_file_schema_uri, "gs://") && output.external_table_contracts["alunos"].dataset_id == "bronze_restricted"
    error_message = "External Parquet deve usar arquivo de schema de referência e autodetect desligado."
  }
  assert {
    condition     = alltrue([for contract in values(output.external_table_contracts) : length(regexall("\\*", one(contract.source_uris))) == 1 && endswith(one(contract.source_uris), "*.parquet")])
    error_message = "Cada external table deve usar exatamente um wildcard GCS suportado pelo BigQuery."
  }
  assert {
    condition = (
      strcontains(output.stream_demo_workflow_contract, "correlation_id") &&
      strcontains(output.stream_demo_workflow_contract, "CORRELATION_ID") &&
      strcontains(output.stream_demo_workflow_contract, "raw_start_offset") &&
      strcontains(output.stream_demo_workflow_contract, "COUNT(DISTINCT event_id)") &&
      strcontains(output.stream_demo_workflow_contract, "int(stream_result.body.rows[0].f[0].v) == 8") &&
      strcontains(output.stream_demo_workflow_contract, "except:") &&
      strcontains(output.stream_demo_workflow_contract, "JOB_STATE_CANCELLED") &&
      strcontains(output.stream_demo_workflow_contract, "connector_params") &&
      strcontains(output.stream_demo_workflow_contract, "additionalUserLabels") &&
      strcontains(output.stream_demo_workflow_contract, "RUN_ID") &&
      strcontains(output.stream_demo_workflow_contract, "valid_table:") &&
      strcontains(output.stream_demo_workflow_contract, "quarantine_table:") &&
      !strcontains(output.stream_demo_workflow_contract, "output_table:") &&
      strcontains(output.stream_demo_workflow_contract, "googleapis.dataflow.v1b3.projects.locations.flexTemplates.launch") &&
      strcontains(output.stream_demo_workflow_contract, "googleapis.dataflow.v1b3.projects.locations.jobs.get") &&
      strcontains(output.stream_demo_workflow_contract, "googleapis.dataflow.v1b3.projects.locations.jobs.update") &&
      !strcontains(output.stream_demo_workflow_contract, "seconds: 600")
    )
    error_message = "O demo deve correlacionar arquivo e oito eventos Silver da execução atual, sem espera fixa."
  }
  assert {
    condition     = output.silver_alunos_partition_expiration_ms == 31536000000
    error_message = "Partições Silver de alunos devem expirar em 365 dias."
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
    condition     = output.lifecycle_contracts["landing"][0].age == 7 && output.lifecycle_contracts["bronze"][0].age == 730 && contains(output.lifecycle_contracts["bronze"][0].prefix, "bronze/alunos/") && length(output.lifecycle_contracts["streaming"]) == 2
    error_message = "Retenções precisam ser landing 7d, alunos Bronze 730d e streaming/quarentena 30d."
  }
  assert {
    condition     = output.security_contract.basic_owner_or_editor_grants == [] && output.security_contract.restricted_student_dataset == "silver_restricted" && output.security_contract.bronze_student_dataset == "bronze_restricted" && output.security_contract.bronze_batch_can_delete == false && output.security_contract.deletion_protection
    error_message = "O contrato negativo deve impedir papéis básicos, PII fora do restrito e deletes Bronze."
  }
  assert {
    condition     = google_storage_bucket_iam_member.batch_bronze_creator.role == "roles/storage.objectCreator" && google_storage_bucket_iam_member.batch_bronze_viewer.role == "roles/storage.objectViewer" && alltrue([for binding in values(local.dataset_bindings) : binding.account != "batch" || !contains(["bronze_restricted", "silver_restricted"], binding.dataset)])
    error_message = "Batch não pode deletar Bronze nem ler datasets restritos de alunos."
  }
  assert {
    condition = (
      contains(local.project_roles.workflow, "roles/bigquery.jobUser") &&
      local.dataset_bindings["workflow:silver:roles/bigquery.dataViewer"].role == "roles/bigquery.dataViewer"
    )
    error_message = "A identidade do Workflow precisa executar consulta e ler apenas o Silver para verificar a correlação."
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
      output.runtime_entrypoint_contract.jobs["producer"].args[0] == "--mode"
    )
    error_message = "Os jobs devem expor os entrypoints reais validados no SHA integrado."
  }
  assert {
    condition = (
      strcontains(output.stream_demo_workflow_contract, "--target, cloud") &&
      strcontains(output.stream_demo_workflow_contract, "--project-dir, dbt") &&
      strcontains(output.stream_demo_workflow_contract, "--profiles-dir, dbt")
    )
    error_message = "O override dbt do demo deve preservar target e diretórios reais da imagem."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_GCP_PROJECT_ID"] == "fiap-fase2-test" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_MAX_BYTES_BILLED"] == "26843545600" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_GIT_SHA"] == "0123456789abcdef0123456789abcdef01234567" &&
      output.runtime_entrypoint_contract.jobs["batch"].env["ALFABETIZACAO_IMAGE_DIGEST"] == "us-docker.pkg.dev/fiap-fase2-test/pipeline/batch@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    error_message = "O job Batch deve receber o ambiente prefixado lido por AppSettings."
  }
  assert {
    condition = (
      output.runtime_entrypoint_contract.jobs["dbt"].env["GCP_PROJECT_ID"] == "fiap-fase2-test" &&
      output.runtime_entrypoint_contract.jobs["dbt"].env["DBT_LOCATION"] == "southamerica-east1"
    )
    error_message = "O job dbt deve receber projeto e localização descobertos pelo stack."
  }
  assert {
    condition = (
      strcontains(output.batch_workflow_contract, "containerOverrides") &&
      strcontains(output.batch_workflow_contract, "--execute") &&
      alltrue([for source in ["uf", "meta_alfabetizacao_brasil", "meta_alfabetizacao_uf", "meta_alfabetizacao_municipio", "municipio", "alunos"] : strcontains(output.batch_workflow_contract, source)])
    )
    error_message = "O Workflow mensal deve executar as seis fontes com fonte, ano e modo explícitos."
  }
}

run "teardown_requires_explicit_protection_change" {
  command = plan
  variables { deletion_protection = false }
  assert {
    condition = (
      output.runtime_contract.jobs["batch"].deletion_protection == false &&
      output.security_contract.deletion_protection == false &&
      alltrue(values(output.runtime_contract.storage_force_destroy))
    )
    error_message = "O apply preparatório deve remover as proteções gerenciadas antes do destroy."
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

run "rejects_non_brl_implicit_budget" {
  command = plan
  variables {
    budget_currency = "USD"
    budget_amount   = null
  }
  expect_failures = [check.budget_contract]
}

run "rejects_mutable_images" {
  command = plan
  variables { batch_image = "us-docker.pkg.dev/fiap-fase2-test/pipeline/batch:latest" }
  expect_failures = [var.batch_image]
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
