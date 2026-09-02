from pathlib import Path
from typing import Final

import pytest

from tests.sql.bigquery_script_runner import ScriptAssertionError, run_bigquery_script
from tests.sql.evaluate_release_harness import create_quality_database, persist_quality_results
from tests.sql.release_script_harness import promotion_options

PROMOTE_RELEASE: Final = Path("src/alfabetizacao_pipeline/releases/templates/promote_release.sql")
PROPORTION_FIELDS: Final = tuple(f"proporcao_aluno_nivel_{level}" for level in range(9))


def _null_update(table: str, column: str) -> str:
    return "update {table} set {column} = null where release_id = 'release-b'".format_map(
        {"table": table, "column": column}
    )


REQUIRED_NULL_CASES: Final = (
    *(
        (
            _null_update(table, "taxa_alfabetizacao"),
            ("percentage_ranges",),
        )
        for table in ("silver_municipio", "silver_uf")
    ),
    *(
        (
            _null_update(table, field),
            ("percentage_ranges", "proportions_sum"),
        )
        for table in ("silver_municipio", "silver_uf")
        for field in PROPORTION_FIELDS
    ),
    *(
        (
            _null_update(table, field),
            ("percentage_ranges",),
        )
        for table in (
            "silver_meta_alfabetizacao_municipio",
            "silver_meta_alfabetizacao_uf",
            "silver_meta_alfabetizacao_brasil",
        )
        for field in ("taxa_alfabetizacao", "percentual_participacao")
    ),
    (
        _null_update("indicador_municipio", "taxa_alfabetizacao"),
        ("gold_core_nulls",),
    ),
    (
        _null_update("comparativo_meta_resultado", "taxa_resultado"),
        ("gold_core_nulls",),
    ),
    (
        _null_update("comparativo_meta_resultado", "meta_alfabetizacao"),
        ("gold_core_nulls",),
    ),
)
OPTIONAL_TARGET_NULL_SQL: Final = tuple(
    _null_update(table, f"meta_alfabetizacao_{year}")
    for table in (
        "silver_meta_alfabetizacao_municipio",
        "silver_meta_alfabetizacao_uf",
        "silver_meta_alfabetizacao_brasil",
    )
    for year in range(2025, 2031)
    if table != "silver_meta_alfabetizacao_brasil" or year != 2030
)


@pytest.mark.parametrize(("defect_sql", "critical_rules"), REQUIRED_NULL_CASES)
def test_required_percentage_null_is_critical_and_blocks_promotion(
    defect_sql: str, critical_rules: tuple[str, ...]
) -> None:
    with create_quality_database() as connection:
        _ = connection.execute(defect_sql)
        persist_quality_results(connection)
        actual = connection.execute(
            "select rule_id from release_results where severity = 'critical' order by rule_id"
        ).fetchall()
        assert actual == [(rule,) for rule in sorted(critical_rules)]
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE_RELEASE,
                options=promotion_options("release-b"),
            )


def test_optional_mean_and_unselected_annual_targets_do_not_become_critical() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "update silver_municipio set media_portugues = null where release_id = 'release-b'"
        )
        for update_sql in OPTIONAL_TARGET_NULL_SQL:
            _ = connection.execute(update_sql)
        persist_quality_results(connection)
        assert connection.execute(
            "select count(*) from release_results where severity = 'critical'"
        ).fetchone() == (0,)
        assert connection.execute(
            "select severity, details from release_results where rule_id = 'optional_null_delta'"
        ).fetchone() == ("warning", "media_portugues_pp_delta")
        run_bigquery_script(
            connection,
            PROMOTE_RELEASE,
            options=promotion_options("release-b"),
        )


def test_brasil_public_2030_target_when_missing_blocks_promotion() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            """
            update silver_meta_alfabetizacao_brasil
            set meta_alfabetizacao_2030 = null
            where release_id = 'release-b' and rede = 'publica'
            """
        )
        persist_quality_results(connection)
        assert connection.execute(
            """
            select metric_value, severity, action
            from release_results
            where rule_id = 'percentage_ranges'
            """
        ).fetchone() == (1.0, "critical", "quarantine_and_block")
        with pytest.raises(ScriptAssertionError):
            run_bigquery_script(
                connection,
                PROMOTE_RELEASE,
                options=promotion_options("release-b"),
            )
