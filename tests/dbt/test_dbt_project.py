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


def test_sqlfluff_lints_dbt_models_from_repository_root() -> None:
    result = subprocess.run(
        [
            "sqlfluff",
            "lint",
            "dbt/models",
            "sql/quality/evaluate_release.sql",
            "sql/quality/promote_release.sql",
            "sql/quality/rollback_release.sql",
            "sql/quality/cleanup_releases.sql",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
