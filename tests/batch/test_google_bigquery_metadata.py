from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Never

import pytest

from alfabetizacao_pipeline.batch.adapters import SourceLocator
from alfabetizacao_pipeline.batch.google_bigquery import NativeBigQueryClient
from alfabetizacao_pipeline.batch.models import BigQueryType


@dataclass(frozen=True, slots=True)
class NativeDatasetMetadata:
    location: str


@dataclass(frozen=True, slots=True)
class NativeSchemaField:
    name: str
    field_type: str
    mode: str


@dataclass(frozen=True, slots=True)
class NativeTableMetadata:
    schema: tuple[NativeSchemaField, ...]
    modified: datetime
    etag: str


class MetadataOnlyNativeClient:
    def __init__(self, schema: tuple[NativeSchemaField, ...] | None = None) -> None:
        self.dataset_refs: list[str] = []
        self.table_refs: list[str] = []
        self.query_calls: int = 0
        self.schema: tuple[NativeSchemaField, ...] = schema or (
            NativeSchemaField("ano", "INTEGER", "REQUIRED"),
            NativeSchemaField("taxa", "FLOAT", "NULLABLE"),
            NativeSchemaField("rede", "STRING", "NULLABLE"),
        )

    def get_dataset(self, dataset_ref: str) -> NativeDatasetMetadata:
        self.dataset_refs.append(dataset_ref)
        return NativeDatasetMetadata(location="US")

    def get_table(self, table_ref: str) -> NativeTableMetadata:
        self.table_refs.append(table_ref)
        return NativeTableMetadata(
            schema=self.schema,
            modified=datetime(2026, 8, 31, tzinfo=UTC),
            etag="native-etag",
        )

    def query(self, statement: str, /) -> Never:
        del statement
        self.query_calls += 1
        message = "metadata inspection must not submit a query job"
        raise AssertionError(message)


def test_native_bigquery_inspection_reads_ordered_metadata_without_a_query_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MetadataOnlyNativeClient()

    def factory(*, project: str) -> MetadataOnlyNativeClient:
        del project
        return client

    monkeypatch.setattr(
        "alfabetizacao_pipeline.batch.google_bigquery.bigquery.Client",
        factory,
    )

    inspection = NativeBigQueryClient("project").inspect(
        SourceLocator("basedosdados", "dataset", "uf")
    )

    assert client.dataset_refs == ["basedosdados.dataset"]
    assert client.table_refs == ["basedosdados.dataset.uf"]
    assert client.query_calls == 0
    assert inspection.identity.location == "US"
    assert inspection.identity.modified_at == datetime(2026, 8, 31, tzinfo=UTC)
    assert inspection.identity.etag == "native-etag"
    assert tuple((column.name, column.data_type, column.mode) for column in inspection.columns) == (
        ("ano", BigQueryType.INT64, "REQUIRED"),
        ("taxa", BigQueryType.FLOAT64, "NULLABLE"),
        ("rede", BigQueryType.STRING, "NULLABLE"),
    )


@pytest.mark.parametrize(
    ("field", "error"),
    [
        (NativeSchemaField("rede", "BOOL", "NULLABLE"), "unsupported-source-column-type"),
        (NativeSchemaField("rede", "STRING", "REPEATED"), "unsupported-source-column-mode"),
    ],
)
def test_native_bigquery_inspection_rejects_unsupported_metadata_without_a_query_job(
    monkeypatch: pytest.MonkeyPatch,
    field: NativeSchemaField,
    error: str,
) -> None:
    client = MetadataOnlyNativeClient((field,))

    def factory(*, project: str) -> MetadataOnlyNativeClient:
        del project
        return client

    monkeypatch.setattr(
        "alfabetizacao_pipeline.batch.google_bigquery.bigquery.Client",
        factory,
    )

    with pytest.raises(ValueError, match=error):
        _ = NativeBigQueryClient("project").inspect(SourceLocator("basedosdados", "dataset", "uf"))

    assert client.query_calls == 0
