from pathlib import Path
from typing import NotRequired, TypedDict

from pydantic import TypeAdapter

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.sql import build_select_sql


class CatalogSource(TypedDict):
    name: str
    policy: str
    keys: list[str]
    columns: list[str]
    classification: NotRequired[str]


class CatalogDocument(TypedDict):
    sources: list[CatalogSource]


def test_catalog_contains_six_official_sources_when_loaded() -> None:
    names = tuple(SOURCE_CATALOG)
    assert names == (
        "uf",
        "meta_alfabetizacao_brasil",
        "meta_alfabetizacao_uf",
        "meta_alfabetizacao_municipio",
        "municipio",
        "alunos",
    )


def test_catalog_keeps_official_keys_when_loaded() -> None:
    keys = {name: contract.key_columns for name, contract in SOURCE_CATALOG.items()}
    assert keys["uf"] == ("ano", "sigla_uf", "rede")
    assert keys["alunos"] == ("ano", "id_municipio", "id_escola", "id_aluno")
    assert keys["meta_alfabetizacao_brasil"] == ("ano", "rede")
    assert keys["meta_alfabetizacao_uf"] == ("ano", "sigla_uf", "rede")
    assert keys["meta_alfabetizacao_municipio"] == ("ano", "id_municipio", "rede")
    assert keys["municipio"] == ("ano", "id_municipio", "rede")


def test_versioned_catalog_matches_executable_source_catalog() -> None:
    catalog_path = Path(__file__).parents[2] / "contracts" / "sources" / "catalog.json"
    document = TypeAdapter(CatalogDocument).validate_json(catalog_path.read_text(encoding="utf-8"))
    documented = {item["name"]: item for item in document["sources"]}

    assert tuple(documented) == tuple(SOURCE_CATALOG)
    for name, contract in SOURCE_CATALOG.items():
        source = documented[name]
        assert source["keys"] == list(contract.key_columns)
        assert source["columns"] == [column.name for column in contract.columns]
        assert source["policy"] == contract.selection_policy.value
    assert documented["alunos"].get("classification") == "restricted"


def test_select_uses_explicit_columns_when_built() -> None:
    contract = SOURCE_CATALOG["municipio"]
    select_sql = build_select_sql(contract, "basedosdados", "br_inep_avaliacao_alfabetizacao", 2024)
    assert "SELECT *" not in select_sql.upper()
    assert "id_municipio" in select_sql
    assert "WHERE ano = @year" in select_sql
    assert "2024" not in select_sql
