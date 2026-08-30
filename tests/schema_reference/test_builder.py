from pathlib import Path

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.schema_reference.builder import (
    build_reference_file,
    inspect_reference_file,
)


def test_reference_parquet_has_zero_rows_and_exact_schema_when_built(tmp_path: Path) -> None:
    # Given: the pinned UF source contract
    output = tmp_path / "reference.parquet"
    # When: a reference schema artifact is built
    descriptor = build_reference_file(SOURCE_CATALOG["uf"], output)
    inspection = inspect_reference_file(output)
    # Then: it has no data, exact columns and an immutable content path descriptor
    assert inspection.row_count == 0
    assert inspection.column_names == tuple(column.name for column in SOURCE_CATALOG["uf"].columns)
    assert descriptor.schema_hash
    assert descriptor.reference_file_schema_uri.endswith(f"/{descriptor.schema_hash}.parquet")
