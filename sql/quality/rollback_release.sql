declare active_rows int64;
declare current_release string;
declare rollback_release string;

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
assert rollback_release is not null as 'no prior release available for rollback';

begin transaction;
update `{{ project_id }}.ops.active_release`
set
    release_id = rollback_release,
    prior_release_id = current_release,
    promoted_at = current_timestamp()
where singleton_key = true;
update `{{ project_id }}.ops.release_registry` set status = 'inactive'
where release_id = current_release;
update `{{ project_id }}.ops.release_registry` set status = 'active'
where release_id = rollback_release;
commit transaction;
