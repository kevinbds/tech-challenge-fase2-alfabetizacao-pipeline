declare active_rows int64;
declare current_release string;
declare rollback_release string;
declare current_registry_rows int64;
declare current_registry_state_rows int64;
declare prior_registry_rows int64;
declare prior_registry_state_rows int64;

begin transaction;
set active_rows = (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';
set (current_release, rollback_release) = (
    select as struct
        release_id,
        prior_release_id
    from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert current_release is not null as 'active release pointer cannot be null';
assert rollback_release is not null as 'no prior release available for rollback';
assert rollback_release != current_release as 'active release cannot reference itself as prior';

set current_registry_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = current_release
);
set current_registry_state_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = current_release and status = 'active'
);
assert (
    current_registry_rows = 1 and current_registry_state_rows = 1
) as 'current release must resolve to exactly one active registry row';

set prior_registry_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = rollback_release
);
set prior_registry_state_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = rollback_release and status = 'inactive'
);
assert (
    prior_registry_rows = 1 and prior_registry_state_rows = 1
) as 'prior release must resolve to exactly one inactive registry row';

update `{{ project_id }}.ops.active_release`
set
    release_id = rollback_release,
    prior_release_id = current_release,
    promoted_at = current_timestamp()
where
    singleton_key = true
    and release_id = current_release
    and prior_release_id = rollback_release;
assert @@row_count = 1 as 'active release pointer changed during rollback';

update `{{ project_id }}.ops.release_registry`
set status = 'inactive'
where release_id = current_release and status = 'active';
assert @@row_count = 1 as 'current registry row changed during rollback';

update `{{ project_id }}.ops.release_registry`
set status = 'active'
where release_id = rollback_release and status = 'inactive';
assert @@row_count = 1 as 'prior registry row changed during rollback';
commit transaction;
