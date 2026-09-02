declare target_year int64 default @reference_year;
declare current_release string;
declare current_prior string;
declare current_year int64;
declare current_baseline string;
declare target_depth int64;
declare rollback_release string;
declare rollback_baseline string;

begin transaction;
assert target_year between 2000 and 2100 as 'invalid reference_year';
assert (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key
) = 1 as 'active release singleton is invalid';
set (
    current_release, current_prior) = (
    select as struct
        release_id,
        prior_release_id
    from `{{ project_id }}.ops.active_release`
    where singleton_key
);
assert (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = current_release and status = 'active'
) = 1
as 'active release registry row is invalid';
assert (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where status = 'active'
) = 1 as 'release registry must contain one active row';
set (
    current_year, current_baseline) = (
    select as struct
        reference_year,
        baseline_release_id
    from `{{ project_id }}.ops.release_registry`
    where release_id = current_release and status = 'active'
);
assert current_baseline is not null as 'no business release is active';
assert current_prior is not distinct from
if(current_baseline = '__bootstrap__', null, current_baseline)
as 'active pointer differs from registry baseline';
assert target_year <= current_year as 'rollback target cannot be newer than active release';
create temp table rollback_chain as
with recursive lineage as (
    select
        release_id,
        reference_year,
        baseline_release_id,
        status,
        0 as chain_level,
        concat('|', release_id, '|') as release_path,
        false as has_cycle
    from `{{ project_id }}.ops.release_registry`
    where release_id = current_release
    union all
    select
        parent.release_id,
        parent.reference_year,
        parent.baseline_release_id,
        parent.status,
        child.chain_level + 1 as chain_level,
        concat(child.release_path, parent.release_id, '|') as release_path,
        strpos(child.release_path, concat('|', parent.release_id, '|')) > 0 as has_cycle
    from lineage as child
    inner join `{{ project_id }}.ops.release_registry` as parent
        on child.baseline_release_id = parent.release_id
    where
        child.baseline_release_id != '__bootstrap__'
        and not child.has_cycle and child.chain_level < 400
)

select * from lineage;
assert (select count(*) from rollback_chain)
= (select count(distinct release_id) from rollback_chain)
as 'release ancestry is ambiguous';
assert not exists (
    select 1 from rollback_chain
    where has_cycle
)
as 'release ancestry contains a cycle';
assert not exists (
    select 1 from rollback_chain
    where chain_level = 400 and baseline_release_id != '__bootstrap__'
)
as 'release ancestry exceeds maximum depth';
assert (
    select count(*) from rollback_chain
    where baseline_release_id = '__bootstrap__'
) = 1
as 'release ancestry is dangling';
assert not exists (
    select 1 from rollback_chain
    where case when chain_level = 0 then status != 'active' else status != 'inactive' end
)
as 'release ancestry statuses are inconsistent';
assert not exists (
    select 1 from rollback_chain as child
    inner join rollback_chain as parent on child.baseline_release_id = parent.release_id
    where child.reference_year < parent.reference_year
)
as 'release ancestry years are inconsistent';
set target_depth = (
    select min(chain_level) from rollback_chain
    where reference_year = target_year
);
assert target_depth is not null as 'rollback target year is absent from active history';
assert (
    select count(*) from rollback_chain
    where reference_year = target_year and chain_level = target_depth
) = 1
as 'rollback target year is ambiguous';
set (
    rollback_release, rollback_baseline) = (
    select as struct
        release_id,
        baseline_release_id
    from rollback_chain
    where reference_year = target_year and chain_level = target_depth
);
update `{{ project_id }}.ops.active_release`
set
    release_id = rollback_release,
    prior_release_id = if(rollback_baseline = '__bootstrap__', null, rollback_baseline),
    promoted_at = current_timestamp()
where
    singleton_key and release_id = current_release
    and prior_release_id is not distinct from current_prior
    and rollback_release != current_release;
assert @@row_count = if(rollback_release = current_release, 0, 1)
as 'active release pointer changed during rollback';
update `{{ project_id }}.ops.release_registry`
set status = 'inactive'
where release_id = current_release and status = 'active' and rollback_release != current_release;
assert @@row_count = if(rollback_release = current_release, 0, 1)
as 'current registry row changed during rollback';
update `{{ project_id }}.ops.release_registry`
set status = 'active', promoted_at = current_timestamp()
where release_id = rollback_release and status = 'inactive' and rollback_release != current_release;
assert @@row_count = if(rollback_release = current_release, 0, 1)
as 'target registry row changed during rollback';
assert (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where status = 'active'
) = 1 as 'release registry must contain one active row';
drop table rollback_chain;
commit transaction;
