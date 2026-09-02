from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.models import BigQueryType


def parquet_payload(source: str, seeds: tuple[int, ...]) -> bytes:
    contract = SOURCE_CATALOG[source]
    arrays: list[pa.Array[pa.Scalar[pa.DataType]]] = []
    fields: list[pa.Field[pa.DataType]] = []
    for column in contract.columns:
        data_type = {
            BigQueryType.INT64: pa.int64(),
            BigQueryType.FLOAT64: pa.float64(),
            BigQueryType.STRING: pa.string(),
        }[column.data_type]
        values = {
            BigQueryType.INT64: list(seeds),
            BigQueryType.FLOAT64: [float(seed) for seed in seeds],
            BigQueryType.STRING: [f"{column.name}-{seed}" for seed in seeds],
        }[column.data_type]
        arrays.append(pa.array(values, type=data_type))
        fields.append(pa.field(column.name, data_type, nullable=column.mode == "NULLABLE"))
    table = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    output = pa.BufferOutputStream()
    with pq.ParquetWriter(output, table.schema, compression="snappy") as writer:
        writer.write_table(table)
    return output.getvalue().to_pybytes()
