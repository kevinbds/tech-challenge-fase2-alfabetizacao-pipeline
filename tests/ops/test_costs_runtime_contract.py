from decimal import Decimal
from pathlib import Path

from alfabetizacao_pipeline.ops.costs import estimate_profile, load_catalog


def test_demo_profile_when_stream_template_has_conservative_runtime() -> None:
    template = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")
    profile = load_catalog(Path("ops/cost_profiles.yml")).profiles["demo"]

    runtime_markers = (
        "numWorkers: 1",
        "maxWorkers: 2",
        "workerRegion: '${region}'",
        "enableStreamingEngine: true",
        "diskSizeGb: 30",
        "dataflow_service_options=enable_streaming_engine_resource_based_billing",
    )

    assert all(marker in template for marker in runtime_markers)
    assert profile.dataflow_max_workers == 2
    assert profile.dataflow_runtime_hours == Decimal("0.583333")
    assert profile.dataflow_worker_vcpus == 4
    assert profile.dataflow_worker_memory_gib == Decimal(15)
    assert profile.dataflow_disk_gib == Decimal(30)
    assert profile.dataflow_streaming_engine_compute_unit_hours == Decimal("1.166666")
    assert "target_state: JOB_STATE_RUNNING, max_attempts: 60" in template
    assert "target_state: JOB_STATE_DRAINED, max_attempts: 90" in template
    assert "max_attempts: 60}" in template
    assert "max_attempts: 18, max_pages: 10" in template
    assert "max_attempts: 6}" in template
    assert "max_attempts: 36" in template
    assert profile.workflows_internal_steps == 5000
    assert profile.bigquery_query_count == 243


def test_demo_profile_when_release_and_streaming_paths_succeed() -> None:
    release_template = Path("infra/stack/modules/runtime/templates/batch.yaml").read_text(
        encoding="utf-8"
    )
    streaming_template = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")
    profile = load_catalog(Path("ops/cost_profiles.yml")).profiles["demo"]

    release_success_steps = (
        "- begin_release:",
        "- run_batch:",
        "- complete_release:",
        "- build_candidate:",
        "- evaluate_quality:",
        "- promote_candidate:",
    )
    assert all(step in release_template for step in release_success_steps)
    assert "sources: [uf, meta_alfabetizacao_brasil, meta_alfabetizacao_uf," in release_template
    assert "municipio, alunos]" in release_template
    assert "- publish_fixture:" in streaming_template
    assert "- build_stream_models:" in streaming_template
    assert profile.cloud_run_vcpu_seconds == Decimal(780)
    assert profile.cloud_run_gib_seconds == Decimal(1470)


def test_demo_profile_when_two_cloud_builds_are_planned() -> None:
    image_build = Path("cloudbuild/build-images.yml").read_text(encoding="utf-8")
    verification_build = Path("cloudbuild/verify-images.yml").read_text(encoding="utf-8")
    submission = Path("cloudbuild/submit-images.sh").read_text(encoding="utf-8")
    catalog = load_catalog(Path("ops/cost_profiles.yml"))

    report = estimate_profile(catalog, "demo")

    assert '"machineType": "E2_HIGHCPU_8"' in image_build
    assert '"machineType"' not in verification_build
    assert "--config=cloudbuild/verify-images.yml" in submission
    assert catalog.profiles["demo"].cloud_build_build_images_minutes == Decimal(12)
    assert catalog.profiles["demo"].cloud_build_verify_images_minutes == Decimal(4)
    assert report.cloud_build_build_images == Decimal("1.03")
    assert report.cloud_build_verify_images == Decimal("0.13")
    assert report.cloud_build == Decimal("1.16")
