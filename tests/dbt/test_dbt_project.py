import subprocess
from pathlib import Path

from pydantic import TypeAdapter
from typing_extensions import TypedDict

DBT_DIR = Path("dbt")


class DependsOn(TypedDict):
    nodes: list[str]


class ManifestNode(TypedDict):
    depends_on: DependsOn


class Manifest(TypedDict):
    nodes: dict[str, ManifestNode]


MANIFEST_ADAPTER = TypeAdapter(Manifest)


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


def test_release_metric_manifest_has_all_direct_producer_edges() -> None:
    result = subprocess.run(
        ["dbt", "parse", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = MANIFEST_ADAPTER.validate_json(
        (DBT_DIR / "target" / "manifest.json").read_text(encoding="utf-8")
    )
    nodes = manifest["nodes"]
    percentage_id = "model.alfabetizacao_medallion.release_percentage_metrics"
    metrics_id = "model.alfabetizacao_medallion.release_metrics"
    percentage_dependencies = set(nodes[percentage_id]["depends_on"]["nodes"])
    metric_dependencies = set(nodes[metrics_id]["depends_on"]["nodes"])
    assert percentage_dependencies == {
        f"model.alfabetizacao_medallion.{name}"
        for name in (
            "silver_municipio",
            "silver_uf",
            "silver_meta_alfabetizacao_municipio",
            "silver_meta_alfabetizacao_uf",
            "silver_meta_alfabetizacao_brasil",
        )
    }
    assert {
        f"model.alfabetizacao_medallion.{name}"
        for name in (
            "release_percentage_metrics",
            "silver_municipio",
            "silver_uf",
            "silver_meta_alfabetizacao_municipio",
            "silver_meta_alfabetizacao_uf",
            "silver_meta_alfabetizacao_brasil",
            "silver_alunos",
            "stg_alunos",
            "indicador_municipio",
            "comparativo_meta_resultado",
            "audit_identical_duplicates",
            "quarantine_conflicting_duplicates",
        )
    } <= metric_dependencies
    assert {
        "source.alfabetizacao_medallion.ops.active_release",
        "source.alfabetizacao_medallion.ops.release_registry",
    } <= metric_dependencies
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
            "+release_metrics",
            "--output",
            "name",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert selection.returncode == 0, selection.stdout + selection.stderr
    selected_names = set(selection.stdout.splitlines())
    assert {
        "silver_municipio",
        "silver_uf",
        "silver_alunos",
        "stg_alunos",
        "indicador_municipio",
        "comparativo_meta_resultado",
        "audit_identical_duplicates",
        "quarantine_conflicting_duplicates",
        "release_percentage_metrics",
        "release_metrics",
    } <= selected_names
