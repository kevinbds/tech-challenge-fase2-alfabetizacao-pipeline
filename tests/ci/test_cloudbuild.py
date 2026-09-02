from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
JSON_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
JSON_SEQUENCE: TypeAdapter[list[JsonValue]] = TypeAdapter(list[JsonValue])


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    return JSON_MAPPING.validate_python(value)


def _sequence(value: JsonValue) -> list[JsonValue]:
    return JSON_SEQUENCE.validate_python(value)


def test_cloudbuild_when_definition_is_parsed() -> None:
    path = Path("cloudbuild/build-images.yml")
    config = _mapping(JSON_VALUE.validate_json(path.read_text(encoding="utf-8")))

    substitutions = _mapping(config["substitutions"])
    steps = [_mapping(step) for step in _sequence(config["steps"])]
    step_ids = {str(step["id"]) for step in steps}
    serialized = path.read_text(encoding="utf-8")
    submit = Path("cloudbuild/submit-images.sh").read_text(encoding="utf-8")

    assert substitutions["_REGION"] == "us-central1"
    assert substitutions["_REPOSITORY"] == "alfabetizacao-pipeline"
    assert all("latest" not in str(step) for step in steps)
    assert all("@sha256:" in str(step["name"]) for step in steps)
    assert {
        "build-batch",
        "build-dbt",
        "build-producer",
        "build-dataflow-template",
        "build-dataflow-sdk",
        "build-reference-schemas",
        "publish-reference-schemas",
    } == step_ids
    assert len(steps) == 7
    images = _sequence(config["images"])
    assert len(images) == 5
    assert all("$COMMIT_SHA" in str(image) for image in images)
    assert "$COMMIT_SHA" in serialized
    assert "docker push" not in serialized
    assert "cloudbuild/capture-digests.sh" in submit
    assert all(name in serialized for name in ("PROJECT_ID", "COMMIT_SHA"))
    assert "requestedVerifyOption" in serialized
    assert "--gcs-source-staging-dir" in submit
    assert "_ARTIFACT_BUCKET=$GCP_ARTIFACT_BUCKET" in submit
    assert "credentials" not in serialized.lower()
    assert "key.json" not in serialized.lower()


def test_remote_smoke_uses_only_captured_digests_and_publishes_report() -> None:
    verify_path = Path("cloudbuild/verify-images.yml")
    verify = _mapping(JSON_VALUE.validate_json(verify_path.read_text(encoding="utf-8")))
    steps = [_mapping(step) for step in _sequence(verify["steps"])]
    substitutions = _mapping(verify["substitutions"])
    artifacts = _mapping(verify["artifacts"])
    objects = _mapping(artifacts["objects"])
    submit = Path("cloudbuild/submit-images.sh").read_text(encoding="utf-8")

    image_substitutions = {
        "_BATCH_IMAGE",
        "_DBT_IMAGE",
        "_PRODUCER_IMAGE",
        "_DATAFLOW_TEMPLATE_IMAGE",
        "_DATAFLOW_SDK_IMAGE",
    }
    assert image_substitutions <= set(substitutions)
    assert len(steps) == 9
    assert str(steps[-1]["id"]) == "write-runtime-smoke-report"
    assert all(
        str(substitutions[key]).endswith("@sha256:" + "0" * 64) for key in image_substitutions
    )
    assert {str(step["name"]) for step in steps[:-1]} == {
        "${_BATCH_IMAGE}",
        "${_DBT_IMAGE}",
        "${_PRODUCER_IMAGE}",
        "${_DATAFLOW_TEMPLATE_IMAGE}",
        "${_DATAFLOW_SDK_IMAGE}",
    }
    dataflow = [step for step in steps if str(step["id"]).startswith("smoke-dataflow-")]
    dbt_parse = next(step for step in steps if step["id"] == "smoke-dbt-parse")
    dataflow_scripts = "\n".join(str(_sequence(step["args"])[-1]) for step in dataflow)
    assert len(dataflow) == 4
    assert {str(step["name"]) for step in dataflow} == {
        "${_DATAFLOW_TEMPLATE_IMAGE}",
        "${_DATAFLOW_SDK_IMAGE}",
    }
    assert sum("entrypoint" not in step for step in dataflow) == 2
    assert "--help" in dataflow_scripts
    assert "apache_beam.__version__ == '2.75.0'" in dataflow_scripts
    assert "import beam_entrypoint" in dataflow_scripts
    assert dbt_parse["args"] == [
        "parse",
        "--project-dir",
        "/app/project/dbt",
        "--profiles-dir",
        "/app/project/dbt",
        "--target",
        "offline",
    ]
    assert objects["paths"] == ["runtime-smoke.json"]
    assert "--config=cloudbuild/verify-images.yml" in submit
    assert "--no-source" in submit
    assert all(f"{key}=" in submit for key in image_substitutions)
    assert "--arg verification_build_id" in submit
    assert "--arg runtime_smoke_uri" in submit
    assert "$verification_build_id" in submit
    assert "runtime-smoke/$verification_build_id/runtime-smoke.json" in submit
    assert "'. + {verification_build_id: $verification_build_id" in submit
    assert "printf 'verification_build_id=" not in submit


def test_runtime_smoke_report_uses_python_available_in_its_pinned_builder() -> None:
    verify = _mapping(
        JSON_VALUE.validate_json(Path("cloudbuild/verify-images.yml").read_text(encoding="utf-8"))
    )
    steps = [_mapping(step) for step in _sequence(verify["steps"])]
    report_step = next(step for step in steps if step["id"] == "write-runtime-smoke-report")
    report_arguments = _sequence(report_step["args"])
    report_command = "\n".join(str(argument) for argument in report_arguments)

    assert report_step["name"] == (
        "gcr.io/google.com/cloudsdktool/google-cloud-cli@"
        "sha256:016179f3641ec13de55083342cb6b2018c7ead2e5eefbaff74db14f7d587b5f1"
    )
    assert "python3" in report_command
    assert "jq " not in report_command
    assert report_arguments[0] == "-ceu"
    assert "/workspace/runtime-smoke.json" in report_command
    assert "BUILD_ID=$BUILD_ID" in _sequence(report_step["env"])


def test_cloudbuild_submit_always_selects_the_dedicated_build_identity() -> None:
    submit = Path("cloudbuild/submit-images.sh").read_text(encoding="utf-8")

    assert submit.count("--service-account=") == 2
    assert (
        submit.count("projects/$GCP_PROJECT_ID/serviceAccounts/$GCP_CLOUD_BUILD_SERVICE_ACCOUNT")
        == 2
    )


def test_runtime_image_copy_matches_five_artifacts_and_eight_smokes() -> None:
    runbook = Path("docs/runbooks.md").read_text(encoding="utf-8")
    finops = Path("docs/finops.md").read_text(encoding="utf-8")
    stack_readme = Path("infra/stack/README.md").read_text(encoding="utf-8")
    template_spec = Path("contracts/events/dataflow-flex-template-spec.example.json").read_text(
        encoding="utf-8"
    )

    assert ".images | length == 5" in runbook
    assert "construir as cinco imagens" in finops
    assert "oito passos de smoke (nove etapas contando o relatório)" in finops
    assert "relatório aprovado dessas cinco\nimagens" in stack_readme
    assert "/dataflow-template@sha256:" in template_spec


def test_cloudbuild_when_uploading_source_excludes_local_credentials() -> None:
    cloudignore = Path(".gcloudignore").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    excluded = (cloudignore, dockerignore, gitignore)

    assert all("gha-creds-*.json" in content for content in excluded)
    assert all("*.tfvars" in content for content in excluded)
    assert all("backend.hcl" in content for content in excluded)
    assert ".git" in cloudignore
    assert ".gcloudignore" in cloudignore
