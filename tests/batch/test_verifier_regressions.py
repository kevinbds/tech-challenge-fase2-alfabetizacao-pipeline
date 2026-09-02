from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from alfabetizacao_pipeline.batch.catalog import SOURCE_CATALOG
from alfabetizacao_pipeline.batch.commands import app as batch_app
from alfabetizacao_pipeline.batch.errors import LandingSchemaError
from alfabetizacao_pipeline.batch.fakes import InMemoryObjectStore
from alfabetizacao_pipeline.batch.models import BatchManifest
from alfabetizacao_pipeline.batch.runner import validate_landing_parquet
from alfabetizacao_pipeline.batch.sql import build_select_sql
from alfabetizacao_pipeline.cli import app as root_app


def _wrong_physical_parquet(*, compression: Literal["gzip", "snappy"]) -> bytes:
    contract = SOURCE_CATALOG["uf"]
    schema = pa.schema([pa.field(column.name, pa.string()) for column in contract.columns])
    rows = [{column.name: "wrong" for column in contract.columns}]
    buffer = pa.BufferOutputStream()
    with pq.ParquetWriter(buffer, schema, compression=compression) as writer:
        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
    return buffer.getvalue().to_pybytes()


@pytest.mark.parametrize("compression", ["gzip", "snappy"])
def test_landing_rejects_wrong_physical_types_even_when_names_match(
    compression: Literal["gzip", "snappy"],
) -> None:
    payload = _wrong_physical_parquet(compression=compression)
    with pytest.raises(LandingSchemaError):
        _ = validate_landing_parquet(payload, "uf")


def test_landing_rejects_non_snappy_codec_even_when_schema_matches() -> None:
    contract = SOURCE_CATALOG["uf"]
    fields = {
        "INT64": pa.int64(),
        "FLOAT64": pa.float64(),
        "STRING": pa.string(),
    }
    schema = pa.schema(
        [pa.field(column.name, fields[column.data_type.value]) for column in contract.columns]
    )
    row = {
        column.name: 1
        if column.data_type.value == "INT64"
        else 1.0
        if column.data_type.value == "FLOAT64"
        else "x"
        for column in contract.columns
    }
    buffer = pa.BufferOutputStream()
    with pq.ParquetWriter(buffer, schema, compression="gzip") as writer:
        writer.write_table(pa.Table.from_pylist([row], schema=schema))
    with pytest.raises(LandingSchemaError):
        _ = validate_landing_parquet(buffer.getvalue().to_pybytes(), "uf")


def test_fake_object_integrity_uses_crc32c_not_crc32() -> None:
    store = InMemoryObjectStore()
    result = store.write_immutable("gs://bronze/vector.parquet", b"123456789")
    assert result.crc32c == "4waSgw=="


def test_queries_bind_year_as_parameter_instead_of_interpolating_it() -> None:
    contract = SOURCE_CATALOG["uf"]
    selection = build_select_sql(contract, "project", "dataset", 2024)
    assert "WHERE ano = @year" in selection
    assert "2024" not in selection


def test_root_cli_mounts_each_command_group_once() -> None:
    runner = CliRunner()
    results = tuple(
        runner.invoke(root_app, [group, "--help"])
        for group in ("batch", "release", "schema-reference")
    )
    duplicate_alias = runner.invoke(root_app, ["releases", "--help"])
    assert tuple(result.exit_code for result in results) == (0, 0, 0)
    assert duplicate_alias.exit_code != 0


def test_fixture_execution_requires_explicit_demo_flag() -> None:
    result = CliRunner().invoke(
        batch_app,
        ["run", "--source", "uf", "--year", "2024", "--execute"],
    )
    if result.exit_code == 0:
        manifest = BatchManifest.model_validate_json(result.stdout)
        assert manifest.git_sha != "local-fixture"
