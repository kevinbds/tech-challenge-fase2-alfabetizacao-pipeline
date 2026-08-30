from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.sql import build_fingerprint_sql, build_select_sql


def test_catalog_contains_six_official_sources_when_loaded() -> None:
    # Given: the versioned official source catalog
    # When: its source identifiers are collected
    names = tuple(SOURCE_CATALOG)
    # Then: only the six challenge tables are present
    assert names == (
        "uf",
        "meta_alfabetizacao_brasil",
        "meta_alfabetizacao_uf",
        "meta_alfabetizacao_municipio",
        "municipio",
        "alunos",
    )


def test_catalog_keeps_official_keys_when_loaded() -> None:
    # Given: the six official contracts
    # When: their keys are inspected
    keys = {name: contract.key_columns for name, contract in SOURCE_CATALOG.items()}
    # Then: every documented key is exact
    assert keys["uf"] == ("ano", "sigla_uf", "rede")
    assert keys["alunos"] == ("ano", "id_municipio", "id_escola", "id_aluno")
    assert keys["meta_alfabetizacao_brasil"] == ("ano", "rede")
    assert keys["meta_alfabetizacao_uf"] == ("ano", "sigla_uf", "rede")
    assert keys["meta_alfabetizacao_municipio"] == ("ano", "id_municipio", "rede")
    assert keys["municipio"] == ("ano", "id_municipio", "rede")


def test_select_and_fingerprint_use_explicit_columns_when_built() -> None:
    # Given: the municipality contract
    contract = SOURCE_CATALOG["municipio"]
    # When: both statements are generated from the contract
    select_sql = build_select_sql(contract, "basedosdados", "br_inep_avaliacao_alfabetizacao", 2024)
    fingerprint_sql = build_fingerprint_sql(
        contract, "basedosdados", "br_inep_avaliacao_alfabetizacao", 2024
    )
    # Then: projections and identity remain explicit
    assert "SELECT *" not in select_sql.upper()
    assert "COUNT(*) AS row_count" in fingerprint_sql
    assert "BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(STRUCT(" in fingerprint_sql
    assert "id_municipio" in fingerprint_sql
    assert "WHERE ano = 2024" in fingerprint_sql
