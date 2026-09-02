from pathlib import Path

from tests.sql.bigquery_script_runner import run_bigquery_script
from tests.sql.release_script_harness import release_database

CLEANUP = Path("sql/quality/cleanup_releases.sql")


def test_cleanup_preserves_every_old_ancestor_of_the_active_release() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            update active_release set release_id = 'release-d', prior_release_id = 'release-c';
            update release_registry
            set status = 'succeeded', created_at = current_timestamp - interval 31 day
            where release_id in ('release-a', 'release-b');
            insert into release_registry(
                release_id, status, created_at, promoted_at, completed_at, baseline_release_id
            ) values
                ('release-c', 'succeeded', current_timestamp - interval 31 day, null,
                 current_timestamp, 'release-b'),
                ('release-d', 'active', current_timestamp, current_timestamp,
                 current_timestamp, 'release-c'),
                ('succeeded-outside-lineage', 'succeeded', current_timestamp - interval 31 day,
                 null, current_timestamp, '__bootstrap__');
            insert into release_files values
                ('release-a', 'a.csv'), ('release-b', 'b.csv'),
                ('release-c', 'c.csv'), ('release-d', 'd.csv'),
                ('succeeded-outside-lineage', 'expired.csv');
            """
        )

        run_bigquery_script(connection, CLEANUP)

        assert connection.execute(
            "select release_id from release_registry order by release_id"
        ).fetchall() == [("release-a",), ("release-b",), ("release-c",), ("release-d",)]
        assert connection.execute(
            "select release_id from release_files order by release_id"
        ).fetchall() == [("release-a",), ("release-b",), ("release-c",), ("release-d",)]


def test_cleanup_does_not_truncate_a_long_valid_lineage() -> None:
    with release_database() as connection:
        _ = connection.execute(
            """
            insert into release_registry
            select
                'lineage-' || lpad(cast(i as varchar), 3, '0'),
                case when i = 401 then 'active' else 'succeeded' end,
                2024,
                current_timestamp - interval 31 day,
                case when i = 401 then current_timestamp else null end,
                current_timestamp,
                case
                    when i = 0 then '__bootstrap__'
                    else 'lineage-' || lpad(cast(i - 1 as varchar), 3, '0')
                end
            from range(402) as lineage(i);
            insert into release_files
            select
                'lineage-' || lpad(cast(i as varchar), 3, '0'),
                'source.csv'
            from range(402) as lineage(i);
            update active_release
            set release_id = 'lineage-401', prior_release_id = 'lineage-400';
            """
        )

        run_bigquery_script(connection, CLEANUP)

        assert connection.execute(
            "select count(*) from release_registry where release_id like 'lineage-%'"
        ).fetchone() == (402,)
        assert connection.execute(
            "select count(*) from release_files where release_id like 'lineage-%'"
        ).fetchone() == (402,)
