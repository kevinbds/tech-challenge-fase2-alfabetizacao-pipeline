from datetime import datetime

from google.cloud import bigquery

from alfabetizacao_pipeline.batch.models import BatchManifest, BatchStatus
from alfabetizacao_pipeline.batch.release_models import ReleaseExecution
from alfabetizacao_pipeline.batch.release_store import (
    RELEASE_SOURCES,
    IncompleteReleaseError,
    ReleaseConflictError,
)


class BigQueryReleaseStore:
    """Transactional BigQuery implementation of the release registry."""

    def __init__(self, project: str, location: str, maximum_bytes_billed: int) -> None:
        """Create a bounded client for one project and BigQuery location."""
        self._project: str = project
        self._location: str = location
        self._maximum_bytes_billed: int = maximum_bytes_billed
        self._client: bigquery.Client = bigquery.Client(project=project)

    def begin(self, execution: ReleaseExecution) -> None:
        """Open or replay the validated release identity."""
        self._execute(
            """
            begin transaction;
            insert into `{project}.ops.release_registry`
              (release_id,status,reference_year,created_at)
            select '__bootstrap__','active',null,current_timestamp()
            from unnest([1])
            where not exists (select 1 from `{project}.ops.active_release`)
              and not exists (select 1 from `{project}.ops.release_registry`
                where release_id='__bootstrap__');
            insert into `{project}.ops.active_release`
              (singleton_key,release_id,prior_release_id,promoted_at)
            select true,'__bootstrap__',null,current_timestamp()
            from unnest([1])
            where not exists (select 1 from `{project}.ops.active_release`);
            assert (select count(*) from `{project}.ops.active_release` where singleton_key)=1
              as 'active release singleton is invalid';
            assert (select count(*) from `{project}.ops.release_registry`
              where release_id=@release_id)<=1
              as 'duplicate release registry row';
            assert (select count(*) from `{project}.ops.release_registry`
              where release_id=@release_id)=0 or (select count(*)
              from `{project}.ops.release_registry` where release_id=@release_id
              and reference_year=@year)=1 as 'release year or state conflict';
            delete from `{project}.ops.release_files` where release_id=@release_id
              and exists (select 1 from `{project}.ops.release_registry`
                where release_id=@release_id and status='failed' and reference_year=@year);
            update `{project}.ops.release_registry`
            set status='running',created_at=current_timestamp(),completed_at=null,promoted_at=null
                ,baseline_release_id=(select release_id from `{project}.ops.active_release`
                  where singleton_key)
            where release_id=@release_id and status='failed' and reference_year=@year;
            insert into `{project}.ops.release_registry`
              (release_id,status,reference_year,created_at,baseline_release_id)
            select @release_id,'running',@year,current_timestamp(),release_id
            from `{project}.ops.active_release` where singleton_key
              and not exists (select 1 from `{project}.ops.release_registry`
                where release_id=@release_id);
            assert (select count(*) from `{project}.ops.release_registry`
              where release_id=@release_id and reference_year=@year
              and status in ('running','succeeded','active','inactive'))=1
              as 'release state or year conflict';
            commit transaction;
            """,
            execution,
        )

    def record(self, execution: ReleaseExecution, manifest: BatchManifest) -> None:
        """Persist immutable Bronze mappings for one completed source run."""
        if (
            manifest.status is not BatchStatus.COMPLETED
            or manifest.completed_at is None
            or manifest.verified_at is None
        ):
            raise ReleaseConflictError(reason="mapping requires a completed manifest")
        if manifest.source not in RELEASE_SOURCES or manifest.year != execution.year:
            raise ReleaseConflictError(reason="mapping source or year differs from release")
        if not manifest.bronze_objects or manifest.row_count <= 0:
            raise IncompleteReleaseError(missing_sources=(manifest.source,))
        for bronze in manifest.bronze_objects:
            self._execute(
                """
                begin transaction;
                assert (select count(*) from `{project}.ops.release_registry`
                  where release_id=@release_id and reference_year=@year
                  and status in ('running','succeeded','active','inactive'))=1
                  as 'release state or year conflict';
                assert @source in unnest({sources}) as 'source is not in the release catalog';
                assert (select count(*) from `{project}.ops.release_files`
                  where release_id=@release_id and table_name=@source and file_uri=@file_uri
                  and (source_run_id!=@run_id or row_count!=@row_count
                    or gcs_generation!=@generation or crc32c!=@crc32c
                    or ingested_at!=@ingested_at or verified_at!=@verified_at))=0
                  as 'release mapping conflict';
                if (select status from `{project}.ops.release_registry`
                    where release_id=@release_id)='running' then
                  insert into `{project}.ops.release_files`
                    (release_id,table_name,ano,file_uri,source_run_id,row_count,status,
                     gcs_generation,crc32c,ingested_at,verified_at)
                  select @release_id,@source,@year,@file_uri,@run_id,@row_count,'selected',
                    @generation,@crc32c,@ingested_at,@verified_at
                  where not exists (select 1 from `{project}.ops.release_files`
                    where release_id=@release_id and table_name=@source and file_uri=@file_uri);
                else
                  assert (select count(*) from `{project}.ops.release_files`
                    where release_id=@release_id and table_name=@source and file_uri=@file_uri)=1
                    as 'terminal release mapping is immutable';
                end if;
                commit transaction;
                """,
                execution,
                source=manifest.source,
                file_uri=bronze.uri,
                run_id=manifest.run_id,
                row_count=manifest.row_count,
                generation=bronze.generation,
                crc32c=bronze.crc32c,
                ingested_at=manifest.completed_at,
                verified_at=manifest.verified_at,
            )

    def complete(self, execution: ReleaseExecution) -> None:
        """Complete only a release containing the exact six non-empty sources."""
        self._execute(
            """
            begin transaction;
            assert (select count(*) from `{project}.ops.release_registry`
              where release_id=@release_id and reference_year=@year
              and status in ('running','succeeded','active','inactive'))=1
              as 'release state or year conflict';
            assert (select count(distinct table_name) from `{project}.ops.release_files`
              where release_id=@release_id and status='selected' and row_count>0)=6
              as 'release requires six non-empty sources';
            assert (select count(*) from unnest({sources}) source where source not in
              (select table_name from `{project}.ops.release_files`
               where release_id=@release_id))=0 as 'release source set differs from catalog';
            assert (select count(*) from (select table_name
              from `{project}.ops.release_files` where release_id=@release_id
              group by table_name having count(distinct source_run_id)!=1))=0
              as 'each source requires exactly one source run';
            update `{project}.ops.release_registry`
            set status='succeeded',completed_at=current_timestamp()
            where release_id=@release_id and reference_year=@year and status='running';
            commit transaction;
            """,
            execution,
        )

    def fail(self, execution: ReleaseExecution) -> None:
        """Fail an unpublished release idempotently."""
        self._execute(
            """
            begin transaction;
            update `{project}.ops.release_registry`
            set status='failed',completed_at=current_timestamp()
            where release_id=@release_id and reference_year=@year
              and status in ('running','succeeded');
            assert @@row_count=1 or (select count(*) from `{project}.ops.release_registry`
              where release_id=@release_id and status='failed' and reference_year=@year)=1
              as 'release cannot transition to failed';
            commit transaction;
            """,
            execution,
        )

    def _execute(
        self,
        script: str,
        execution: ReleaseExecution,
        **values: str | int | datetime,
    ) -> None:
        parameters = [
            bigquery.ScalarQueryParameter("release_id", "STRING", execution.release_id),
            bigquery.ScalarQueryParameter("year", "INT64", execution.year),
        ]
        parameters.extend(
            bigquery.ScalarQueryParameter(
                name,
                _parameter_type(value),
                value.isoformat() if isinstance(value, datetime) else value,
            )
            for name, value in values.items()
        )
        rendered = script.format(
            project=self._project,
            sources="[" + ",".join(f"'{source}'" for source in RELEASE_SOURCES) + "]",
        )
        job = self._client.query(
            rendered,
            location=self._location,
            job_config=bigquery.QueryJobConfig(
                query_parameters=parameters,
                maximum_bytes_billed=self._maximum_bytes_billed,
            ),
        )
        _ = tuple(job.result())


def _parameter_type(value: str | int | datetime) -> str:
    if isinstance(value, datetime):
        return "TIMESTAMP"
    if isinstance(value, int):
        return "INT64"
    return "STRING"
