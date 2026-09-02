from pathlib import Path

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.ops.costs import load_catalog
from alfabetizacao_pipeline.ops.models import CostRequest

CATALOG = Path("ops/cost_profiles.yml")


def test_bigquery_total_when_each_query_respects_the_individual_cap() -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data.update(
        bigquery_total_bytes_processed=26 * 1024**3,
        bigquery_query_count=2,
        bigquery_max_bytes_billed_per_query=25 * 1024**3,
    )

    request = CostRequest.model_validate(data)

    assert request.bigquery_total_bytes_processed == 26 * 1024**3


@pytest.mark.parametrize(
    "changes",
    [
        {"bigquery_max_bytes_billed_per_query": 26 * 1024**3},
    ],
)
def test_bigquery_input_when_individual_cap_exceeds_the_configured_limit(
    changes: dict[str, int],
) -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data.update(changes)

    with pytest.raises(ValidationError):
        _ = CostRequest.model_validate(data)


def test_bigquery_total_when_control_queries_are_not_subject_to_the_analytic_cap() -> None:
    data = load_catalog(CATALOG).profiles["demo"].model_dump()
    data.update(
        bigquery_total_bytes_processed=375 * 1024**3,
        bigquery_query_count=243,
        bigquery_max_bytes_billed_per_query=25 * 1024**3,
    )

    request = CostRequest.model_validate(data)

    assert request.bigquery_total_bytes_processed == 375 * 1024**3
