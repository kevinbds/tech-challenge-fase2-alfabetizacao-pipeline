declare candidate_release string default @release_id;
declare current_release string;
declare active_rows int64;
declare critical_failures int64;

set active_rows
= (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';

set critical_failures = (
    select count(*) from `{{ project_id }}.quality.release_results`
    where release_id = candidate_release and severity = 'critical'
);
assert critical_failures = 0 as 'candidate release has critical quality failures';

set current_release = (
    select release_id from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);

begin transaction;
update `{{ project_id }}.ops.active_release`
set
    prior_release_id = current_release,
    release_id = candidate_release,
    promoted_at = current_timestamp()
where singleton_key = true;

update `{{ project_id }}.ops.release_registry`
set status = 'active', promoted_at = current_timestamp()
where release_id = candidate_release;

update `{{ project_id }}.ops.release_registry`
set status = 'inactive'
where release_id = current_release;
commit transaction;
