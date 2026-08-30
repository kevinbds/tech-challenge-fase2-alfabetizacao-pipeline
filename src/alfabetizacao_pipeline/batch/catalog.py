from typing import Final

from alfabetizacao_pipeline.batch.models import (
    BigQueryType,
    SelectionPolicy,
    SourceColumn,
    SourceContract,
)

PINNED_SCHEMA_COMMIT: Final = "fa95c5d79286471d2b9158670c927ec7bc73d6fa"


def _column(name: str, data_type: str) -> SourceColumn:
    return SourceColumn(name=name, data_type=BigQueryType(data_type), mode="NULLABLE")


_LEVEL_COLUMNS: Final = tuple(
    _column(f"proporcao_aluno_nivel_{level}", "FLOAT64") for level in range(9)
)
_RESULT_COLUMNS: Final = (
    _column("ano", "INT64"),
    _column("serie", "STRING"),
    _column("rede", "STRING"),
    _column("taxa_alfabetizacao", "FLOAT64"),
    _column("media_portugues", "FLOAT64"),
    *_LEVEL_COLUMNS,
)
_META_COLUMNS: Final = (
    _column("ano", "INT64"),
    _column("rede", "STRING"),
    _column("taxa_alfabetizacao", "FLOAT64"),
    *tuple(_column(f"meta_alfabetizacao_{year}", "FLOAT64") for year in range(2024, 2031)),
)


def _contract(
    name: str,
    columns: tuple[SourceColumn, ...],
    keys: tuple[str, ...],
) -> SourceContract:
    return SourceContract(
        name=name,
        columns=columns,
        key_columns=keys,
        selection_policy=SelectionPolicy.ANNUAL,
        pinned_schema_commit=PINNED_SCHEMA_COMMIT,
    )


SOURCE_CATALOG: Final = {
    "uf": _contract(
        "uf",
        (_column("ano", "INT64"), _column("sigla_uf", "STRING"), *_RESULT_COLUMNS[1:]),
        ("ano", "sigla_uf", "rede"),
    ),
    "meta_alfabetizacao_brasil": _contract(
        "meta_alfabetizacao_brasil",
        (*_META_COLUMNS, _column("percentual_participacao", "FLOAT64")),
        ("ano", "rede"),
    ),
    "meta_alfabetizacao_uf": _contract(
        "meta_alfabetizacao_uf",
        (
            _column("ano", "INT64"),
            _column("sigla_uf", "STRING"),
            *_META_COLUMNS[1:],
            _column("percentual_participacao", "FLOAT64"),
        ),
        ("ano", "sigla_uf", "rede"),
    ),
    "meta_alfabetizacao_municipio": _contract(
        "meta_alfabetizacao_municipio",
        (
            _column("ano", "INT64"),
            _column("id_municipio", "STRING"),
            *_META_COLUMNS[1:],
            _column("nivel_alfabetizacao", "INT64"),
            _column("percentual_participacao", "FLOAT64"),
        ),
        ("ano", "id_municipio", "rede"),
    ),
    "municipio": _contract(
        "municipio",
        (_column("ano", "INT64"), _column("id_municipio", "STRING"), *_RESULT_COLUMNS[1:]),
        ("ano", "id_municipio", "rede"),
    ),
    "alunos": _contract(
        "alunos",
        tuple(
            _column(name, data_type)
            for name, data_type in (
                ("ano", "INT64"),
                ("id_municipio", "STRING"),
                ("id_escola", "STRING"),
                ("id_aluno", "STRING"),
                ("caderno", "STRING"),
                ("serie", "STRING"),
                ("rede", "STRING"),
                ("presenca", "STRING"),
                ("preenchimento_caderno", "STRING"),
                ("alfabetizado", "STRING"),
                ("proficiencia", "FLOAT64"),
                ("peso_aluno", "FLOAT64"),
            )
        ),
        ("ano", "id_municipio", "id_escola", "id_aluno"),
    ),
}
