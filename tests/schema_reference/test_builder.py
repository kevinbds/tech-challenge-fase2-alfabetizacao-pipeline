from pathlib import Path

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.schema_reference.builder import (
    build_demo_file,
    build_reference_file,
    inspect_reference_file,
)


def test_reference_parquet_has_zero_rows_and_exact_schema_when_built(tmp_path: Path) -> None:
    output = tmp_path / "reference.parquet"
    descriptor = build_reference_file(SOURCE_CATALOG["uf"], output)
    inspection = inspect_reference_file(output)
    assert inspection.row_count == 0
    assert inspection.column_names == tuple(column.name for column in SOURCE_CATALOG["uf"].columns)
    assert descriptor.schema_hash
    assert descriptor.model_dump() == {
        "source": "uf",
        "schema_hash": descriptor.schema_hash,
        "local_path": output,
    }


def test_demo_parquet_has_one_row_when_built(tmp_path: Path) -> None:
    output = tmp_path / "demo.parquet"
    build_demo_file(SOURCE_CATALOG["uf"], output, year=2024)

    assert inspect_reference_file(output).row_count == 1
