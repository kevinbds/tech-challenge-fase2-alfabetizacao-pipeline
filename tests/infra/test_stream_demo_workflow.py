import re
from pathlib import Path

import yaml
from pydantic import JsonValue, TypeAdapter

JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_STEPS: TypeAdapter[list[dict[str, JsonValue]]] = TypeAdapter(list[dict[str, JsonValue]])
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def _workflow() -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(
        JSON_VALUE.validate_python(
            yaml.safe_load(Path("workflows/stream_demo.yaml").read_text(encoding="utf-8"))
        )
    )


def _steps(container: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    return {
        name: JSON_MAPPING.validate_python(value)
        for step in JSON_STEPS.validate_python(container["steps"])
        for name, value in step.items()
    }


def _main_steps() -> dict[str, dict[str, JsonValue]]:
    return _steps(JSON_MAPPING.validate_python(_workflow()["main"]))


def _assignments(step: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        name: value
        for assignment in JSON_STEPS.validate_python(step["assign"])
        for name, value in assignment.items()
    }


def _guarded_execution_steps() -> dict[str, dict[str, JsonValue]]:
    guarded_execution = JSON_MAPPING.validate_python(_main_steps()["guarded_execution"])
    return _steps(JSON_MAPPING.validate_python(guarded_execution["try"]))


def _final_backlog_steps() -> dict[str, dict[str, JsonValue]]:
    final_evidence = JSON_MAPPING.validate_python(
        _guarded_execution_steps()["check_final_evidence"]
    )
    branches = JSON_STEPS.validate_python(
        JSON_MAPPING.validate_python(final_evidence["parallel"])["branches"]
    )
    backlog_branch = JSON_MAPPING.validate_python(
        next(branch["backlog_branch"] for branch in branches if "backlog_branch" in branch)
    )
    return _steps(backlog_branch)


def test_stream_demo_reads_infrastructure_only_from_workflow_environment() -> None:
    steps = _main_steps()
    assigned = _assignments(steps["init"])
    requested = _assignments(steps["read_input"])
    launch_flex = _guarded_execution_steps()["launch_flex"]
    launch_args = JSON_MAPPING.validate_python(launch_flex["args"])
    launch_body = JSON_MAPPING.validate_python(launch_args["body"])
    launch_parameter = JSON_MAPPING.validate_python(launch_body["launchParameter"])
    environment = JSON_MAPPING.validate_python(launch_parameter["environment"])
    assert JSON_MAPPING.validate_python(_workflow()["main"])["params"] == ["args"]
    assert assigned["project_id"] == '${sys.get_env("GOOGLE_CLOUD_PROJECT_ID")}'
    assert assigned["region"] == '${sys.get_env("GOOGLE_CLOUD_LOCATION")}'
    assert assigned["dataflow_sdk_container_image"] == (
        '${sys.get_env("ALFABETIZACAO_DATAFLOW_SDK_CONTAINER_IMAGE")}'
    )
    assert requested == {
        "action": '${default(map.get(args, "action"), "run")}',
        "release_year": '${map.get(args, "release_year")}',
    }
    assert environment["sdkContainerImage"] == "${dataflow_sdk_container_image}"
    assert assigned["valid_query_table"] == '${text.replace_all(valid_staging_table, ":", ".")}'
    assert assigned["quarantine_query_table"] == '${text.replace_all(quarantine_table, ":", ".")}'


def test_stream_demo_rejects_invalid_input_before_reading_release_year() -> None:
    steps = _main_steps()
    map_guard = JSON_STEPS.validate_python(steps["require_map_input"]["switch"])
    key_guard = JSON_STEPS.validate_python(steps["require_supported_input"]["switch"])
    assert list(steps)[:4] == [
        "require_map_input",
        "validate_input_keys",
        "require_supported_input",
        "read_input",
    ]
    assert map_guard[0]["condition"] == '${get_type(args) != "map"}'
    assert (
        map_guard[0]["raise"] == "A entrada deve ser um objeto com release_year e action opcional"
    )
    assert key_guard[0]["condition"] == (
        '${len(input_keys) > 2 or not("release_year" in input_keys) or '
        '(len(input_keys) == 2 and not("action" in input_keys))}'
    )
    assert key_guard[0]["raise"] == "Somente release_year e action são aceitos"
    assert _assignments(steps["read_input"])["release_year"] == '${map.get(args, "release_year")}'


def test_stream_demo_uses_fixed_correlated_queries_and_monitoring_signals() -> None:
    main_assignments = _assignments(_main_steps()["init"])
    execution_steps = _guarded_execution_steps()

    primary_by_name = _steps(
        JSON_MAPPING.validate_python(_workflow()["wait_main_subscription_backlogs"])
    )
    backlog_args = JSON_MAPPING.validate_python(primary_by_name["read_backlog_metric"]["args"])
    backlog_query = JSON_MAPPING.validate_python(backlog_args["query"])
    backlog_filter = str(backlog_query["filter"])
    query_body = JSON_MAPPING.validate_python(
        JSON_MAPPING.validate_python(
            _steps(JSON_MAPPING.validate_python(_workflow()["wait_bigquery_count"]))["query_count"][
                "args"
            ]
        )["body"]
    )
    wait_backlog_args = JSON_MAPPING.validate_python(
        _final_backlog_steps()["wait_main_backlogs"]["args"]
    )
    assert query_body["maximumBytesBilled"] == "${maximum_bytes_billed}"
    assert "COUNT(DISTINCT event_id)" in str(main_assignments["silver_query"])
    assert "COUNT(DISTINCT event_fingerprint)" in str(main_assignments["quarantine_query"])
    assert wait_backlog_args["main_subscription_ids"] == (
        "${[backlog_subscription_ids[0], backlog_subscription_ids[1]]}"
    )
    assert primary_by_name["verify_subscription_exists"]["call"] == (
        "googleapis.pubsub.v1.projects.subscriptions.get"
    )
    assert primary_by_name["read_backlog_metric"]["call"] == "http.get"
    assert backlog_args["auth"] == {"type": "OAuth2"}
    assert backlog_args["url"] == (
        '${"https://monitoring.googleapis.com/v3/projects/"'
        ' + project_id + "/timeSeries"}'
    )
    assert "pubsub.googleapis.com/subscription/num_undelivered_messages" in backlog_filter
    assert primary_by_name["require_time_series"] == {
        "switch": [{"condition": "${len(time_series) == 0}", "next": "retry_or_fail"}]
    }
    assert primary_by_name["require_metric_point"] == {
        "switch": [{"condition": "${len(metric_points) == 0}", "next": "retry_or_fail"}]
    }
    assert "${int(metric_points[0].value.int64Value) != 0}" in str(
        primary_by_name["require_empty_subscription"]
    )
    build_stream_models_args = JSON_MAPPING.validate_python(
        JSON_MAPPING.validate_python(execution_steps["build_stream_models"])["args"]
    )
    assert build_stream_models_args["connector_params"] == {"timeout": 3900}


def test_stream_demo_scans_dead_letter_metric_pages_after_visibility_barrier() -> None:
    dead_letter_by_name = _steps(
        JSON_MAPPING.validate_python(_workflow()["wait_no_dead_letter_events"])
    )
    dead_letter_step_names = list(dead_letter_by_name)
    dead_letter_args = JSON_MAPPING.validate_python(
        dead_letter_by_name["read_dead_letter_metric"]["args"]
    )
    dead_letter_query = JSON_MAPPING.validate_python(dead_letter_args["query"])
    dead_letter_init = _assignments(dead_letter_by_name["init"])
    metric_page_assign = JSON_STEPS.validate_python(
        dead_letter_by_name["capture_metric_page"]["assign"]
    )
    choose_point_switch = JSON_STEPS.validate_python(dead_letter_by_name["choose_point"]["switch"])
    wait_dead_letter_args = JSON_MAPPING.validate_python(
        _final_backlog_steps()["wait_dead_letter_window"]["args"]
    )
    assert wait_dead_letter_args["dlq_metric_subscription_ids"] == (
        "${[backlog_subscription_ids[0], backlog_subscription_ids[1]]}"
    )
    assert "dead_letter_message_count" in str(dead_letter_query["filter"])
    assert dead_letter_query["pageSize"] == 1000
    assert dead_letter_query["pageToken"] == "${page_token}"
    assert metric_page_assign[1] == {
        "next_page_token": '${default(map.get(dead_letter_metric.body, "nextPageToken"), "")}'
    }
    assert dead_letter_init["dlq_visibility_time"] == "${sys.now() + 300}"
    assert dead_letter_by_name["wait_for_dlq_visibility"]["call"] == "sys.sleep_until"
    assert dead_letter_step_names.index("wait_for_dlq_visibility") < dead_letter_step_names.index(
        "read_dead_letter_metric"
    )
    assert dead_letter_by_name["choose_series"]["next"] == "normalize_points"
    assert dead_letter_by_name["next_page_or_advance"]["next"] == "advance_page"
    assert (
        JSON_STEPS.validate_python(dead_letter_by_name["next_page_or_advance"]["switch"])[0]["next"]
        == "advance_subscription"
    )
    assert JSON_MAPPING.validate_python(choose_point_switch[0])["next"] == "advance_series"
    assert dead_letter_by_name["fail_dead_letter_event"] == {"return": {"success": False}}


def test_dataflow_job_name_is_valid_for_a_concrete_uuid() -> None:
    job_name_expression = _assignments(_main_steps()["init"])["job_name"]
    correlation_id = "12345678-1234-1234-1234-123456789abc"
    job_name = f"literacy-demo-{correlation_id.replace('-', '')[:24]}"
    assert job_name_expression == (
        '${"literacy-demo-" + text.substring(text.replace_all(correlation_id, "-", ""), 0, 24)}'
    )
    assert re.fullmatch(r"[a-z]([-a-z0-9]{0,38}[a-z0-9])?", job_name)


def test_stream_demo_checks_the_active_release_before_launching_dataflow() -> None:
    main_steps = _main_steps()
    main_assignments = _assignments(main_steps["init"])
    check_active_release_body = JSON_MAPPING.validate_python(
        JSON_MAPPING.validate_python(main_steps["check_active_release"]["args"])["body"]
    )
    assert list(main_steps).index("check_active_release") < list(main_steps).index(
        "guarded_execution"
    )
    release_query = str(main_assignments["release_query"])
    assert "release_registry" in release_query
    assert "registry.status = 'active'" in release_query
    assert "active.release_id != '__bootstrap__'" in release_query
    assert "registry.reference_year = @release_year" in release_query
    assert check_active_release_body["maximumBytesBilled"] == "${maximum_bytes_billed}"
    assert check_active_release_body["location"] == "${data_location}"


def test_stream_demo_is_pinned_to_the_verified_2024_release() -> None:
    supported_values = JSON_MAPPING.validate_python(_main_steps()["require_supported_values"])
    release_year_guard = JSON_STEPS.validate_python(supported_values["switch"])[0]
    variables = Path("infra/stack/variables_runtime.tf").read_text(encoding="utf-8")
    assert JSON_MAPPING.validate_python(release_year_guard)["condition"] == (
        '${get_type(release_year) != "integer" or release_year != 2024}'
    )
    assert JSON_MAPPING.validate_python(release_year_guard)["raise"] == (
        "release_year deve ser 2024 para a fixture oficial da demonstração"
    )
    assert "var.stream_release_year == 2024" in variables


def test_runtime_provides_every_custom_workflow_variable_once() -> None:
    init_assignments = _assignments(_main_steps()["init"])
    runtime = Path("infra/stack/modules/runtime/main.tf").read_text(encoding="utf-8")
    environment_block = runtime.partition("user_env_vars = {")[2].partition("\n  }")[0]
    consumed = re.findall(r"ALFABETIZACAO_[A-Z_]+", " ".join(map(str, init_assignments.values())))
    provided = re.findall(r"^\s+(ALFABETIZACAO_[A-Z_]+)\s+=", environment_block, re.MULTILINE)
    assert len(consumed) == len(set(consumed)) == 18
    assert len(provided) == len(set(provided)) == 18
    assert set(consumed) == set(provided)


def test_runtime_passes_only_main_subscriptions_to_backlog_checks() -> None:
    runtime = Path("infra/stack/runtime.tf").read_text(encoding="utf-8")
    assert (
        "backlog_subscription_ids = [module.streaming.archive_subscription_id, "
        "module.streaming.dataflow_subscription_id]"
    ) in runtime
    assert "values(module.streaming.dead_letter_subscription_ids)" not in runtime


def test_flex_template_is_created_before_the_active_object_is_destroyed() -> None:
    runtime = Path("infra/stack/modules/runtime/main.tf").read_text(encoding="utf-8")
    resource = re.search(
        r'resource "google_storage_bucket_object" "flex_template" \{(?P<body>.*?)\n\}',
        runtime,
        flags=re.DOTALL,
    )
    assert resource is not None
    assert "lifecycle {" in resource.group("body")
    assert "create_before_destroy = true" in resource.group("body")


def test_gold_evidence_surface_exposes_the_workflow_correlation() -> None:
    gold_query = _assignments(_main_steps()["init"])["gold_query"]
    gold = Path("dbt/models/gold/indicador_atual_hibrido.sql").read_text(encoding="utf-8")
    assert "simulacao.correlation_id" in gold
    assert "correlation_id = @correlation_id" in str(gold_query)
    assert "origem = 'stream_simulacao'" in str(gold_query)
