from pathlib import Path

import pytest
from google.cloud import bigquery
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.release_bigquery import BigQueryReleaseStore
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution
from tests.sql.bigquery_script_runner import (
    ScriptAssertionError,
    ScriptRunOptions,
    run_bigquery_script,
)
from tests.sql.release_script_harness import release_database


def _execution(year: int) -> ReleaseExecution:
    return ReleaseExecution(
        release_id="batch-202608-y2024-r0123456789ab",
        year=year,
    )


def test_release_execution_rejects_a_year_different_from_its_identifier() -> None:
    with pytest.raises(ValidationError, match="reference year"):
        _ = _execution(2025)


def test_bigquery_failed_reopen_keeps_mappings_when_the_persisted_year_differs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class QueryJob:
        def result(self) -> tuple[()]:
            return ()

    class QueryClient:
        def __init__(self) -> None:
            self.script: str | None = None

        def query(
            self,
            script: str,
            *,
            location: str,
            job_config: bigquery.QueryJobConfig,
        ) -> QueryJob:
            assert location == "US"
            assert job_config.query_parameters is not None
            self.script = script
            return QueryJob()

    client = QueryClient()

    def query_client_factory(project: str | None = None) -> QueryClient:
        assert project == "project"
        return client

    monkeypatch.setattr(bigquery, "Client", query_client_factory)
    store = BigQueryReleaseStore("project", "US", maximum_bytes_billed=7)
    execution = _execution(2024)
    connection = release_database()
    _ = connection.execute(
        """
        insert into release_registry
          (release_id,status,reference_year,created_at,baseline_release_id)
        values (?, 'failed', 2023, current_timestamp, 'release-a')
        """,
        [execution.release_id],
    )
    _ = connection.execute("insert into release_files values (?, 'uf')", [execution.release_id])

    store.begin(execution)

    assert client.script is not None
    script_path = tmp_path / "reopen_release.sql"
    _ = script_path.write_text(
        client.script.replace("`project.ops.release_registry`", "release_registry")
        .replace("`project.ops.active_release`", "active_release")
        .replace("`project.ops.release_files`", "release_files"),
        encoding="utf-8",
    )

    with pytest.raises(ScriptAssertionError, match="release year"):
        run_bigquery_script(
            connection,
            script_path,
            options=ScriptRunOptions(
                parameters={"release_id": execution.release_id, "year": execution.year}
            ),
        )

    assert connection.execute(
        "select count(*) from release_files where release_id=?", [execution.release_id]
    ).fetchone() == (1,)
    assert connection.execute(
        "select status, reference_year from release_registry where release_id=?",
        [execution.release_id],
    ).fetchone() == ("failed", 2023)
