from decimal import Decimal
from pathlib import Path

from alfabetizacao_pipeline.ops.costs import estimate_profile, load_catalog

CATALOG = Path("ops/cost_profiles.yml")


def test_artifact_registry_when_demo_profile_is_estimated_in_gib_month() -> None:
    catalog = load_catalog(CATALOG)

    report = estimate_profile(catalog, "demo")

    assert catalog.profiles["demo"].artifact_registry_gib_month == Decimal("0.50")
    assert catalog.rates.artifact_registry_per_gib_month == Decimal("0.55")
    assert report.artifact_registry_unit == "GiB-month"
    assert report.artifact_registry == Decimal("0.28")
    assert report.total == Decimal("19.50")
