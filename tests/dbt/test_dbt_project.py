import subprocess
from pathlib import Path

DBT_DIR = Path("dbt")


def test_dbt_project_parses_offline() -> None:
    result = subprocess.run(
        ["dbt", "parse", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_gold_models_never_expose_student_identifier() -> None:
    forbidden = "id_" + "aluno"
    for model in (DBT_DIR / "models" / "gold").glob("*.sql"):
        assert forbidden not in model.read_text(encoding="utf-8").lower()


def test_stream_demo_selection_contains_dedupe_audit_and_overlay() -> None:
    selection = subprocess.run(
        [
            "dbt",
            "ls",
            "--quiet",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--select",
            "tag:stream_demo",
            "--resource-type",
            "model",
            "--output",
            "name",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert selection.returncode == 0, selection.stdout + selection.stderr
    assert set(selection.stdout.splitlines()) == {
        "stream_latest",
        "stream_event_audit",
        "indicador_atual_hibrido",
    }


def test_stream_models_are_not_redeclared_as_external_sources() -> None:
    sources = subprocess.run(
        [
            "dbt",
            "ls",
            "--quiet",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--resource-type",
            "source",
            "--output",
            "name",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert sources.returncode == 0, sources.stdout + sources.stderr
    source_names = set(sources.stdout.splitlines())
    assert {"ops.stream_latest", "ops.stream_event_audit"}.isdisjoint(source_names)


def test_sqlfluff_lints_dbt_models_from_repository_root() -> None:
    result = subprocess.run(
        [
            "sqlfluff",
            "lint",
            "dbt/models",
            "sql/quality/evaluate_release.sql",
            "src/alfabetizacao_pipeline/releases/templates/promote_release.sql",
            "src/alfabetizacao_pipeline/releases/templates/rollback_release.sql",
            "sql/quality/cleanup_releases.sql",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_models_are_adapter_portable_and_physically_isolated() -> None:
    macros = "\n".join(
        path.read_text(encoding="utf-8") for path in (DBT_DIR / "macros").glob("*.sql")
    )
    project = (DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8")
    staging = "\n".join(
        path.read_text(encoding="utf-8") for path in (DBT_DIR / "models" / "staging").glob("*.sql")
    )
    sources = (DBT_DIR / "models" / "sources.yml").read_text(encoding="utf-8")
    bronze_macro = (DBT_DIR / "macros" / "bronze_release.sql").read_text(encoding="utf-8")

    assert "adapter.dispatch('safe_cast'" in macros
    assert "safe_cast(" in macros
    assert "try_cast(" in macros
    assert "bigquery__days_since" in macros
    assert "duckdb__days_since" in macros
    assert "{{ safe_cast(" in staging
    assert "safe_cast(ano" not in staging
    assert "bronze.*," in bronze_macro
    assert "bronze.* except (_file_name)" not in bronze_macro
    assert "bronze.* exclude (_file_name)" in bronze_macro
    assert "normalize_municipality_id" in macros
    assert "regexp_contains" in macros
    assert "regexp_full_match" in macros
    assert "lpad(trim(id_municipio)" not in staging
    assert "+incremental_strategy: merge" in project
    for name in ("audit_identical_duplicates.sql", "quarantine_conflicting_duplicates.sql"):
        content = (DBT_DIR / "models" / "quality" / name).read_text(encoding="utf-8")
        assert "incremental_strategy='merge'" in content
    assert "name: bronze_restricted" in sources
