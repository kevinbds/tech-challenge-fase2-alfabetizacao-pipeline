import re
from pathlib import Path
from typing import ClassVar, Final, cast

import yaml
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from sqlglot import exp, parse_one

CATALOG_PATH: Final = Path("config/quality_rules.yml")
MEASUREMENTS_PATH: Final = Path("dbt/models/quality/relationship_measurements.sql")
JSON_MAPPING: Final = TypeAdapter(dict[str, JsonValue])
STRING_VALUE: Final = TypeAdapter(str)

type RelationExpectation = tuple[str, str, tuple[str, ...], dict[str, str]]

EXPECTED_RELATIONS: Final[dict[str, RelationExpectation]] = {
    "alunos_diretorio_municipio": (
        "silver_alunos",
        "diretorios.municipio",
        ("id_municipio",),
        {"release_id": "source"},
    ),
    "municipio_diretorio": (
        "silver_municipio",
        "diretorios.municipio",
        ("id_municipio",),
        {"release_id": "source"},
    ),
    "uf_diretorio": (
        "silver_uf",
        "diretorios.municipio",
        ("sigla_uf",),
        {"release_id": "source"},
    ),
    "meta_municipio_diretorio": (
        "silver_meta_alfabetizacao_municipio",
        "diretorios.municipio",
        ("id_municipio",),
        {"release_id": "source"},
    ),
    "meta_uf_diretorio": (
        "silver_meta_alfabetizacao_uf",
        "diretorios.municipio",
        ("sigla_uf",),
        {"release_id": "source"},
    ),
    "meta_municipio_resultado": (
        "silver_meta_alfabetizacao_municipio",
        "silver_municipio",
        ("release_id", "ano", "id_municipio", "rede"),
        {"release_id": "source", "rede": "municipal"},
    ),
    "resultado_uf_meta": (
        "silver_uf",
        "silver_meta_alfabetizacao_uf",
        ("release_id", "ano", "sigla_uf", "rede"),
        {"release_id": "source", "rede": "publica"},
    ),
}


class RelationContract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    source: str
    target: str
    keys: tuple[str, ...]
    domain: dict[str, str]


class QualityRule(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    id: str
    relations: dict[str, RelationContract] | None = None
    release_scoped: bool | None = None


class QualityCatalog(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    rules: tuple[QualityRule, ...]


def _catalog() -> QualityRule:
    document = JSON_MAPPING.validate_python(
        yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    )
    catalog = QualityCatalog.model_validate(document)
    return next(rule for rule in catalog.rules if rule.id == "relationships")


def _executable_relation_names() -> frozenset[str]:
    sql = MEASUREMENTS_PATH.read_text(encoding="utf-8")
    sql = re.sub(r"^\{\{\s*config.*?\}\}\s*", "", sql, count=1, flags=re.DOTALL)
    sql = re.sub(r"\{\{.*?\}\}", "source_table", sql, flags=re.DOTALL)
    tree = parse_one(sql, read="bigquery")
    names: set[str] = set()
    for alias in tree.find_all(exp.Alias):
        literal = cast("object", alias.this)
        if (
            alias.alias == "relation_name"
            and isinstance(literal, exp.Literal)
            and literal.is_string
        ):
            names.add(STRING_VALUE.validate_python(cast("object", literal.this)))
    return frozenset(names)


def test_documented_relationships_match_executable_model() -> None:
    rule = _catalog()

    assert rule.relations is not None
    assert rule.release_scoped is True
    assert frozenset(rule.relations) == _executable_relation_names()
    assert set(rule.relations) == set(EXPECTED_RELATIONS)

    for name, (source, target, keys, domain) in EXPECTED_RELATIONS.items():
        relation = rule.relations[name]
        assert (relation.source, relation.target) == (source, target)
        assert relation.keys == keys
        assert relation.domain == domain
