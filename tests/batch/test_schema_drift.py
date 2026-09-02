from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.models import BigQueryType, SourceColumn
from alfabetizacao_pipeline.batch.schema_drift import compare_schema


def test_removed_renamed_type_and_mode_are_blocking_when_compared() -> None:
    expected = SOURCE_CATALOG["uf"]
    actual = tuple(
        SourceColumn(name=column.name, data_type=BigQueryType.STRING, mode="REPEATED")
        for column in expected.columns
        if column.name != "sigla_uf"
    )
    result = compare_schema(expected, actual)
    assert result.blocking is True
    assert "sigla_uf" in result.removed_columns
    assert result.type_changes
    assert result.mode_changes


def test_added_column_is_warning_when_compared() -> None:
    expected = SOURCE_CATALOG["uf"]
    actual = (
        *expected.columns,
        SourceColumn(name="campo_novo", data_type=BigQueryType.STRING, mode="NULLABLE"),
    )
    result = compare_schema(expected, actual)
    assert result.blocking is False
    assert result.added_columns == ("campo_novo",)
