from tests.sql.evaluate_release_harness import create_quality_database, persist_quality_results


def test_evaluator_calculates_exact_catalog_from_release_tables() -> None:
    with create_quality_database() as connection:
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select count(*), count(distinct rule_id),
                   count(*) filter (where severity = 'critical')
            from release_results where release_id = 'release-b'
            """
        ).fetchone()
        repeated = connection.execute(
            """
            select metric_value, severity, details from release_results
            where rule_id = 'repeated_evaluation_or_target_rate'
            """
        ).fetchone()
    assert actual == (13, 13, 0)
    assert repeated == (0.0, "pass", "stg_alunos_pre_deduplication")


def test_freshness_uses_current_verification_for_reused_annual_snapshot() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "update release_files set ingested_at = current_timestamp - interval 90 day"
        )

        persist_quality_results(connection)
        freshness = connection.execute(
            """
            select metric_value, severity, action from release_results
            where rule_id = 'pipeline_freshness'
            """
        ).fetchone()

    assert freshness == (0.0, "pass", "promote")


def test_source_defects_change_measured_results_without_metric_parameters() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "insert into stg_alunos select * from stg_alunos where release_id = 'release-b'"
        )
        _ = connection.execute(
            "update silver_municipio set taxa_alfabetizacao = 101 where release_id = 'release-b'"
        )
        _ = connection.execute(
            """update silver_meta_alfabetizacao_brasil
            set meta_alfabetizacao_2030 = -1 where release_id = 'release-b'"""
        )
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select rule_id, severity from release_results
            where rule_id in (
                'non_negative_measurements', 'percentage_ranges',
                'repeated_evaluation_or_target_rate'
            )
            order by rule_id
            """
        ).fetchall()
    assert actual == [
        ("non_negative_measurements", "critical"),
        ("percentage_ranges", "critical"),
        ("repeated_evaluation_or_target_rate", "critical"),
    ]


def test_relationships_measure_missing_directory_and_meta_before_gold_joins() -> None:
    with create_quality_database() as connection:
        _ = connection.execute("delete from municipio")
        _ = connection.execute(
            "delete from silver_meta_alfabetizacao_uf where release_id = 'release-b'"
        )

        persist_quality_results(connection)
        actual = connection.execute(
            """
            select round(metric_value, 6), severity, details from release_results
            where rule_id = 'relationships'
            """
        ).fetchone()

    assert actual is not None
    assert actual[0] == 16.666667
    assert actual[1:] == ("critical", "sete_relacoes_de_referencia")


def test_missing_baseline_is_an_explicit_warning() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            "update release_registry set baseline_release_id = 'missing-baseline' \
where release_id = 'release-b'"
        )
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select rule_id, severity, details from release_results
            where rule_id in ('optional_null_delta', 'partition_volume')
            order by rule_id
            """
        ).fetchall()
    assert actual == [
        ("optional_null_delta", "warning", "baseline_missing"),
        ("partition_volume", "warning", "baseline_missing"),
    ]


def test_known_rr_meta_gap_warns_without_breaking_relationships() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            """
            insert into municipio values ('1400100', 'Boa Vista', 'RR');
            insert into silver_uf values (
                'release-b', 2024, 'RR', 'publica', 70, 200,
                10, 10, 10, 10, 10, 10, 10, 10, 20
            );
            insert into silver_meta_alfabetizacao_uf values (
                'release-b', 2024, 'RR', 'publica', null, null,
                70, 71, 72, 73, 74, 75, 76
            );
            insert into quarantine_meta_alfabetizacao_uf values (
                'release-b', 2024, 'RR', 'publica',
                'meta-uf-rr-2024', current_timestamp,
                'meta_alfabetizacao_uf',
                'taxa_alfabetizacao_and_percentual_participacao_missing'
            );
            """
        )
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select rule_id, severity, metric_value
            from release_results
            where rule_id in ('required_keys', 'relationships', 'percentage_ranges')
            order by rule_id
            """
        ).fetchall()

    assert actual == [
        ("percentage_ranges", "pass", 0.0),
        ("relationships", "pass", 100.0),
        ("required_keys", "warning", 0.0),
    ]


def test_unapproved_meta_gap_is_critical() -> None:
    with create_quality_database() as connection:
        _ = connection.execute(
            """
            insert into quarantine_meta_alfabetizacao_uf values (
                'release-b', 2024, 'SP', 'publica',
                'meta-uf-sp-2024', current_timestamp,
                'meta_alfabetizacao_uf', 'taxa_alfabetizacao_missing'
            );
            """
        )
        persist_quality_results(connection)
        actual = connection.execute(
            """
            select severity, action from release_results
            where rule_id = 'required_keys'
            """
        ).fetchone()

    assert actual == ("critical", "quarantine_and_block")
