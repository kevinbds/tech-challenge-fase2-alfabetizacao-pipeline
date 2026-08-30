from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from alfabetizacao_pipeline.batch.models import BigQueryType
from alfabetizacao_pipeline.batch.sql import schema_hash
from alfabetizacao_pipeline.schema_reference.models import (
    ReferenceSchemaDescriptor,
    ReferenceSchemaInspection,
)

if TYPE_CHECKING:
    from pathlib import Path

    from alfabetizacao_pipeline.batch.models import SourceColumn, SourceContract


def _arrow_field(column: SourceColumn) -> pa.Field[pa.DataType]:
    arrow_types: dict[BigQueryType, pa.DataType] = {
        BigQueryType.INT64: pa.int64(),
        BigQueryType.FLOAT64: pa.float64(),
        BigQueryType.STRING: pa.string(),
    }
    data_type = arrow_types[column.data_type]
    return pa.field(column.name, data_type, nullable=column.mode == "NULLABLE")


def build_reference_file(
    contract: SourceContract,
    output: Path,
) -> ReferenceSchemaDescriptor:
    """Write a zero-row Snappy Parquet schema artifact and its GCS descriptor."""
    arrow_schema = pa.schema([_arrow_field(column) for column in contract.columns])
    table = pa.Table.from_batches([], schema=arrow_schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    with pq.ParquetWriter(output, arrow_schema, compression="snappy") as writer:
        writer.write_table(table)
    digest = schema_hash(contract)
    return ReferenceSchemaDescriptor(
        source=contract.name,
        schema_hash=digest,
        local_path=output,
        reference_file_schema_uri=(
            f"gs://artifacts/reference-schemas/{contract.name}/{digest}.parquet"
        ),
    )


def inspect_reference_file(path: Path) -> ReferenceSchemaInspection:
    """Read row count and ordered columns from a generated Parquet artifact."""
    parquet_file = pq.ParquetFile(path)
    return ReferenceSchemaInspection(
        row_count=parquet_file.metadata.num_rows,
        column_names=tuple(parquet_file.schema_arrow.names),
    )
