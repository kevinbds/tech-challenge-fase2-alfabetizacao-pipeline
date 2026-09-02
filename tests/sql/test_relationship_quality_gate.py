from tests.sql.evaluate_release_harness import (
    create_quality_database,
    persist_quality_results,
)


def test_relationships_block_when_one_expected_relation_is_empty() -> None:
    with create_quality_database() as connection:
        _ = connection.execute("delete from silver_alunos where release_id = 'release-b'")
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select round(metric_value, 6), severity, action, details
            from release_results
            where rule_id = 'relationships'
            """
        ).fetchone()

    assert actual is not None
    assert actual[0] == 85.714286
    assert actual[1:] == (
        "critical",
        "quarantine_and_block",
        "sete_relacoes_de_referencia",
    )
