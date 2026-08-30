from pathlib import Path

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.ops.catalogs import load_observability, load_run_contracts
from alfabetizacao_pipeline.ops.models import RunIdentity


def test_observability_when_catalog_is_loaded() -> None:
    # Given: the machine-readable observability contract.
    catalog = load_observability(Path("ops/observability.yml"))

    # When: alert identifiers and thresholds are projected.
    alert_ids = {alert.alert_id for alert in catalog.alerts}
    slo_ids = {slo.slo_id for slo in catalog.slos}

    # Then: every challenge signal is represented with deploy-time notification routing.
    assert alert_ids == {
        "batch-ingestion-failure",
        "batch-freshness-breach",
        "batch-volume-critical",
        "streaming-latency-p95",
        "dataflow-terminal-failure",
        "dataflow-backlog",
        "streaming-dlq-not-empty",
        "dq-critical",
        "budget-threshold",
    }
    assert slo_ids == {"batch-success", "batch-freshness", "streaming-latency"}
    assert catalog.notification_channel == "${NOTIFICATION_CHANNEL_ID}"
    assert catalog.alert("streaming-latency-p95").threshold == 60
    assert catalog.alert("batch-freshness-breach").threshold == 35
    assert catalog.alert("budget-threshold").signal_type == "budget_notification"


def test_run_contract_when_catalog_is_loaded() -> None:
    # Given: deployment and teardown contracts consumed by automation.
    contracts = load_run_contracts(Path("ops/run-contracts.yml"))

    # When/Then: immutable digests and guarded teardown are mandatory.
    assert contracts.image_reference_pattern == "^.+@sha256:[0-9a-f]{64}$"
    assert contracts.require_git_sha is True
    assert contracts.require_build_id is True
    assert contracts.provenance.required is True
    assert contracts.provenance.sbom_when_available is True
    assert contracts.teardown.requires_confirmation is True
    assert contracts.teardown.drain_streaming_first is True
    assert contracts.teardown.allowed_terminal_state == "DRAINED"


def test_run_identity_when_digest_is_valid() -> None:
    # Given: an immutable image, exact source revision and build identifier.
    data = {
        "image_reference": f"southamerica-east1-docker.pkg.dev/p/r/batch@sha256:{'a' * 64}",
        "git_sha": "b" * 40,
        "build_id": "build-20260829-001",
    }

    # When: the execution identity crosses the validation boundary.
    identity = RunIdentity.model_validate(data)

    # Then: all provenance fields are preserved without a mutable tag.
    assert identity.image_reference.endswith(f"sha256:{'a' * 64}")
    assert identity.git_sha == "b" * 40


def test_run_identity_when_image_uses_tag() -> None:
    # Given: a mutable image tag with otherwise valid provenance.
    data = {
        "image_reference": "southamerica-east1-docker.pkg.dev/p/r/batch:stale",
        "git_sha": "b" * 40,
        "build_id": "build-20260829-001",
    }

    # When/Then: the executable contract rejects stale mutable references.
    with pytest.raises(ValidationError):
        _ = RunIdentity.model_validate(data)


def test_observability_when_document_is_malformed(tmp_path: Path) -> None:
    # Given: a syntactically valid document with an unknown executable field.
    malformed = tmp_path / "observability.yml"
    _ = malformed.write_text('{"version":"1.0","execute":"echo unsafe"}', encoding="utf-8")

    # When/Then: strict parsing rejects config text instead of executing it.
    with pytest.raises(ValidationError):
        _ = load_observability(malformed)
