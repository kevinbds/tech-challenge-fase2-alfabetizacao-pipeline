import subprocess
from pathlib import Path
from typing import NotRequired

from pydantic import TypeAdapter
from typing_extensions import TypedDict

DBT_DIR = Path("dbt")


class DependsOn(TypedDict):
    nodes: list[str]


class NodeConfig(TypedDict):
    full_refresh: NotRequired[bool | None]


class ManifestNode(TypedDict):
    depends_on: DependsOn
    config: NodeConfig


class Manifest(TypedDict):
    nodes: dict[str, ManifestNode]


MANIFEST_ADAPTER = TypeAdapter(Manifest)


def _parse_manifest() -> Manifest:
    result = subprocess.run(
        ["dbt", "parse", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return MANIFEST_ADAPTER.validate_json(
        (DBT_DIR / "target" / "manifest.json").read_text(encoding="utf-8")
    )


def test_release_metric_manifest_has_all_direct_producer_edges() -> None:
    nodes = _parse_manifest()["nodes"]

    def transitive_dependencies(node_id: str) -> set[str]:
        pending = list(nodes[node_id]["depends_on"]["nodes"])
        observed: set[str] = set()
        while pending:
            dependency = pending.pop()
            if dependency in observed:
                continue
            observed.add(dependency)
            if dependency in nodes:
                pending.extend(nodes[dependency]["depends_on"]["nodes"])
        return observed

    percentage_id = "model.alfabetizacao_medallion.release_percentage_metrics"
    metrics_id = "model.alfabetizacao_medallion.release_metrics"
    percentage_dependencies = set(nodes[percentage_id]["depends_on"]["nodes"])
    metric_dependencies = transitive_dependencies(metrics_id)
    comparison_id = "model.alfabetizacao_medallion.comparativo_meta_resultado"
    comparison_dependencies = set(nodes[comparison_id]["depends_on"]["nodes"])
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
            "relationship_measurements",
            "indicador_municipio",
            "comparativo_meta_resultado",
            "audit_identical_duplicates",
            "quarantine_conflicting_duplicates",
            "quarantine_meta_alfabetizacao_uf",
        )
    } <= metric_dependencies
    assert comparison_dependencies == {
        f"model.alfabetizacao_medallion.{name}"
        for name in (
            "indicador_municipio",
            "silver_uf",
            "silver_meta_alfabetizacao_municipio",
            "silver_meta_alfabetizacao_uf",
            "silver_meta_alfabetizacao_brasil",
        )
    } | {"source.alfabetizacao_medallion.diretorios.municipio"}
    assert comparison_id in metric_dependencies
    assert "source.alfabetizacao_medallion.ops.release_registry" in metric_dependencies
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
        "relationship_measurements",
        "indicador_municipio",
        "comparativo_meta_resultado",
        "audit_identical_duplicates",
        "quarantine_conflicting_duplicates",
        "quarantine_meta_alfabetizacao_uf",
        "release_percentage_metrics",
        "release_metrics",
    } <= selected_names


def test_duplicate_audits_cover_every_deduplicated_staging_source() -> None:
    nodes = _parse_manifest()["nodes"]
    candidate_id = "model.alfabetizacao_medallion.duplicate_candidates"
    audit_ids = {
        "model.alfabetizacao_medallion.audit_identical_duplicates",
        "model.alfabetizacao_medallion.quarantine_conflicting_duplicates",
    }
    assert set(nodes[candidate_id]["depends_on"]["nodes"]) == {
        f"model.alfabetizacao_medallion.{name}"
        for name in (
            "stg_municipio",
            "stg_uf",
            "stg_meta_alfabetizacao_municipio",
            "stg_meta_alfabetizacao_uf",
            "stg_meta_alfabetizacao_brasil",
            "stg_alunos",
        )
    }
    for audit_id in audit_ids:
        assert set(nodes[audit_id]["depends_on"]["nodes"]) == {candidate_id}


def test_gold_history_models_ignore_global_full_refresh() -> None:
    manifest = _parse_manifest()
    configs = {
        name: manifest["nodes"][f"model.alfabetizacao_medallion.{name}"]["config"]
        for name in (
            "indicador_municipio",
            "comparativo_meta_resultado",
            "evolucao_alfabetizacao",
        )
    }
    assert all(config.get("full_refresh") is False for config in configs.values())
