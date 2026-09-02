declare active_rows int64;
set active_rows
= (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';

begin transaction;
with recursive active_lineage as (
    select
        registry.release_id,
        registry.baseline_release_id,
        concat('|', registry.release_id, '|') as release_path,
        false as has_cycle
    from `{{ project_id }}.ops.release_registry` as registry
    cross join `{{ project_id }}.ops.active_release` as active
    where
        active.singleton_key
        and (
            registry.release_id = active.release_id
            or registry.release_id = active.prior_release_id
        )

    union all

    select
        parent.release_id,
        parent.baseline_release_id,
        concat(child.release_path, parent.release_id, '|') as release_path,
        strpos(child.release_path, concat('|', parent.release_id, '|')) > 0 as has_cycle
    from active_lineage as child
    inner join `{{ project_id }}.ops.release_registry` as parent
        on child.baseline_release_id = parent.release_id
    where
        child.baseline_release_id != '__bootstrap__'
        and not child.has_cycle
)
delete from `{{ project_id }}.ops.release_files`
where release_id in (
    select registry.release_id
    from `{{ project_id }}.ops.release_registry` as registry
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
    and not exists (
        select 1
        from active_lineage
        where active_lineage.release_id = registry.release_id
    )
);
with recursive active_lineage as (
    select
        registry.release_id,
        registry.baseline_release_id,
        concat('|', registry.release_id, '|') as release_path,
        false as has_cycle
    from `{{ project_id }}.ops.release_registry` as registry
    cross join `{{ project_id }}.ops.active_release` as active
    where
        active.singleton_key
        and (
            registry.release_id = active.release_id
            or registry.release_id = active.prior_release_id
        )

    union all

    select
        parent.release_id,
        parent.baseline_release_id,
        concat(child.release_path, parent.release_id, '|') as release_path,
        strpos(child.release_path, concat('|', parent.release_id, '|')) > 0 as has_cycle
    from active_lineage as child
    inner join `{{ project_id }}.ops.release_registry` as parent
        on child.baseline_release_id = parent.release_id
    where
        child.baseline_release_id != '__bootstrap__'
        and not child.has_cycle
)
delete from `{{ project_id }}.ops.release_registry` as registry
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
and not exists (
    select 1
    from active_lineage
    where active_lineage.release_id = registry.release_id
);
commit transaction;
