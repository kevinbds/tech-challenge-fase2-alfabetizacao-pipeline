declare active_rows int64;
set active_rows
= (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';

begin transaction;
delete from `{{ project_id }}.ops.release_files`
where release_id in (
    select registry.release_id
    from `{{ project_id }}.ops.release_registry` as registry
    cross join `{{ project_id }}.ops.active_release` as active
    where (
        (
            registry.status = 'failed'
            and registry.created_at < timestamp_sub(current_timestamp(), interval 7 day)
        )
        or (
            registry.status = 'succeeded'
            and registry.created_at < timestamp_sub(current_timestamp(), interval 30 day)
        )
    )
    and registry.release_id not in (active.release_id, active.prior_release_id)
);
delete from `{{ project_id }}.ops.release_registry`
where (
    (status = 'failed' and created_at < timestamp_sub(current_timestamp(), interval 7 day))
    or (status = 'succeeded' and created_at < timestamp_sub(current_timestamp(), interval 30 day))
)
and release_id not in (
    select release_id from `{{ project_id }}.ops.active_release`
    where singleton_key = true
    union all
    select prior_release_id from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
commit transaction;
