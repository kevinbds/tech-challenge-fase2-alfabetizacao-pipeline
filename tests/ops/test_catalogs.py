from pathlib import Path
from typing import TypeIs

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.ops.catalogs import (
    AlertContract,
    MetricAlert,
    load_observability,
    load_run_contracts,
)
from alfabetizacao_pipeline.ops.models import RunIdentity


def _is_metric_alert(alert: AlertContract) -> TypeIs[MetricAlert]:
    return alert.signal_type == "monitoring_metric"


def test_observability_when_catalog_is_loaded() -> None:
    catalog = load_observability(Path("ops/observability.yml"))

    metric_types = {
        alert.alert_id: alert.metric_type for alert in catalog.alerts if _is_metric_alert(alert)
    }

    assert metric_types == {
        "cloud-run-job-failure": "logging.googleapis.com/user/${NAME_PREFIX}-batch_failure",
        "data-quality-test-failure": (
            "logging.googleapis.com/user/${NAME_PREFIX}-data_quality_critical"
        ),
        "streaming-latency": ("pubsub.googleapis.com/subscription/oldest_unacked_message_age"),
        "dataflow-terminal-failure": "dataflow.googleapis.com/job/is_failed",
        "workflow-execution-failure": "workflows.googleapis.com/finished_execution_count",
        "archive-backlog": "pubsub.googleapis.com/subscription/num_undelivered_messages",
        "dataflow-backlog": "pubsub.googleapis.com/subscription/num_undelivered_messages",
        "archive-dlq-not-empty": ("pubsub.googleapis.com/subscription/num_undelivered_messages"),
        "dataflow-dlq-not-empty": ("pubsub.googleapis.com/subscription/num_undelivered_messages"),
    }
    assert len(metric_types) == len(catalog.alerts)
    assert catalog.slos == ()
    assert catalog.notification_channel == "${NOTIFICATION_CHANNEL_ID}"
    assert catalog.alert("streaming-latency").threshold == 60
    assert catalog.alert("archive-backlog").duration_seconds == 600
    assert catalog.alert("dataflow-backlog").duration_seconds == 600
    assert catalog.alert("archive-dlq-not-empty").duration_seconds == 60
    assert catalog.alert("dataflow-dlq-not-empty").duration_seconds == 60
    assert all(not metric.startswith("custom.googleapis.com") for metric in metric_types.values())


def test_workflow_failure_alert_when_catalog_and_stack_are_compared() -> None:
    catalog = load_observability(Path("ops/observability.yml"))
    monitoring_source = Path("infra/stack/monitoring.tf").read_text(encoding="utf-8")

    alert = catalog.alert("workflow-execution-failure")
    resource_start = monitoring_source.index(
        'resource "google_monitoring_alert_policy" "workflow_failure" {'
    )
    resource_end = monitoring_source.index(
        '\nresource "google_monitoring_alert_policy"', resource_start + 1
    )
    resource = monitoring_source[resource_start:resource_end]

    assert _is_metric_alert(alert)
    assert alert.metric_type == "workflows.googleapis.com/finished_execution_count"
    assert alert.comparison == "gt"
    assert alert.threshold == 0
    assert alert.duration_seconds == 0
    assert alert.severity == "critical"
    assert 'metric.type=\\"workflows.googleapis.com/finished_execution_count\\"' in resource
    assert 'resource.type=\\"workflows.googleapis.com/Workflow\\"' in resource
    assert 'metric.label.\\"status\\"=\\"FAILED\\"' in resource
    assert 'resource.label.\\"location\\"=\\"${var.region}\\"' in resource
    assert "${module.runtime.workflow_names.batch}" in resource
    assert "${module.runtime.workflow_names.stream_demo}" in resource
    assert 'comparison      = "COMPARISON_GT"' in resource
    assert "threshold_value = 0" in resource
    assert 'duration        = "0s"' in resource
    assert 'alignment_period   = "60s"' in resource
    assert 'per_series_aligner = "ALIGN_SUM"' in resource
    channel_assignment = "notification_channels = var.alert_email == null ? [] : "
    channel_reference = "[google_monitoring_notification_channel.email[0].name]"
    expected_channels = f"{channel_assignment}{channel_reference}"
    assert expected_channels in resource


def test_run_contract_when_catalog_is_loaded() -> None:
    contracts = load_run_contracts(Path("ops/run-contracts.yml"))

    assert contracts.image_reference_pattern == "^.+@sha256:[0-9a-f]{64}$"
    assert contracts.require_git_sha is True
    assert contracts.require_build_id is True
    assert contracts.provenance.required is True
    assert contracts.provenance.sbom_when_available is True
    assert contracts.teardown.requires_confirmation is True
    assert contracts.teardown.drain_streaming_first is True
    assert contracts.teardown.allowed_terminal_state == "DRAINED"


def test_run_identity_when_digest_is_valid() -> None:
    data = {
        "image_reference": f"southamerica-east1-docker.pkg.dev/p/r/batch@sha256:{'a' * 64}",
        "git_sha": "b" * 40,
        "build_id": "build-20260829-001",
    }

    identity = RunIdentity.model_validate(data)

    assert identity.image_reference.endswith(f"sha256:{'a' * 64}")
    assert identity.git_sha == "b" * 40


def test_run_identity_when_image_uses_tag() -> None:
    data = {
        "image_reference": "southamerica-east1-docker.pkg.dev/p/r/batch:stale",
        "git_sha": "b" * 40,
        "build_id": "build-20260829-001",
    }

    with pytest.raises(ValidationError):
        _ = RunIdentity.model_validate(data)


def test_observability_when_document_is_malformed(tmp_path: Path) -> None:
    malformed = tmp_path / "observability.yml"
    _ = malformed.write_text('{"version":"1.0","execute":"echo unsafe"}', encoding="utf-8")

    with pytest.raises(ValidationError):
        _ = load_observability(malformed)
