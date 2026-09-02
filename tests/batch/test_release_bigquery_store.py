from datetime import UTC, datetime
from typing import Protocol, TypedDict

import pytest
from google.cloud import bigquery
from pydantic import TypeAdapter

from alfabetizacao_pipeline.batch.release_bigquery import BigQueryReleaseStore
from tests.batch.release_test_support import completed_manifest, release_execution

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class QueryJobConfigBoundary(Protocol):
    def to_api_repr(self) -> dict[str, JsonValue]: ...


class QueryDocument(TypedDict):
    maximumBytesBilled: str
    queryParameters: list["QueryParameterDocument"]


class QueryParameterValueDocument(TypedDict):
    value: str


class QueryParameterDocument(TypedDict):
    name: str
    parameterValue: QueryParameterValueDocument


class QueryJobConfigDocument(TypedDict):
    query: QueryDocument


class QueryJob:
    def result(self) -> tuple[()]:
        return ()


def test_release_registry_queries_inherit_the_runtime_byte_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[QueryJobConfigBoundary] = []

    class QueryClient:
        def query(
            self,
            _sql: str,
            *,
            location: str,
            job_config: QueryJobConfigBoundary,
        ) -> QueryJob:
            assert location == "US"
            observed.append(job_config)
            return QueryJob()

    def query_client_factory(project: str | None = None) -> QueryClient:
        del project
        return QueryClient()

    monkeypatch.setattr(bigquery, "Client", query_client_factory)
    store = BigQueryReleaseStore("project", "US", maximum_bytes_billed=7)

    store.begin(release_execution())

    config = TypeAdapter(QueryJobConfigDocument).validate_python(observed[0].to_api_repr())
    assert len(observed) == 1
    assert config["query"]["maximumBytesBilled"] == "7"


def test_begin_release_bootstrap_inserts_use_a_bigquery_row_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_sql: list[str] = []

    class QueryClient:
        def query(
            self,
            sql: str,
            *,
            location: str,
            job_config: QueryJobConfigBoundary,
        ) -> QueryJob:
            del job_config
            assert location == "US"
            observed_sql.append(sql)
            return QueryJob()

    def query_client_factory(project: str | None = None) -> QueryClient:
        del project
        return QueryClient()

    monkeypatch.setattr(bigquery, "Client", query_client_factory)

    BigQueryReleaseStore("project", "US", maximum_bytes_billed=7).begin(
        release_execution()
    )

    sql = observed_sql[0].lower()
    assert sql.count("from unnest([1])") == 2


def test_bigquery_release_mapping_persists_both_timestamp_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, QueryJobConfigBoundary]] = []

    class QueryClient:
        def query(
            self,
            sql: str,
            *,
            location: str,
            job_config: QueryJobConfigBoundary,
        ) -> QueryJob:
            assert location == "US"
            observed.append((sql, job_config))
            return QueryJob()

    def query_client_factory(project: str | None = None) -> QueryClient:
        del project
        return QueryClient()

    monkeypatch.setattr(bigquery, "Client", query_client_factory)
    store = BigQueryReleaseStore("project", "US", maximum_bytes_billed=7)
    current_verification = datetime(2026, 10, 30, tzinfo=UTC)

    store.record(
        release_execution(),
        completed_manifest("uf", verified_at=current_verification),
    )

    sql, job_config = observed[0]
    config = TypeAdapter(QueryJobConfigDocument).validate_python(job_config.to_api_repr())
    parameters = {
        parameter["name"]: parameter["parameterValue"]["value"]
        for parameter in config["query"]["queryParameters"]
    }
    assert "ingested_at,verified_at" in sql
    assert parameters["ingested_at"] == "2026-08-30T00:01:00+00:00"
    assert parameters["verified_at"] == current_verification.isoformat()
    assert set(parameters) == {
        "release_id",
        "year",
        "source",
        "file_uri",
        "run_id",
        "row_count",
        "generation",
        "crc32c",
        "ingested_at",
        "verified_at",
    }
