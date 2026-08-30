declare target_release string default @release_id;
declare calculated_rules int64;
declare inserted_rules int64;

begin transaction;

set calculated_rules = (
    select count(*) from `{{ project_id }}.quality.release_metrics`
    where release_id = target_release
);
assert calculated_rules = 13 as 'release metrics must contain exactly 13 catalog rules';

delete from `{{ project_id }}.quality.release_results`
where release_id = target_release;

insert into `{{ project_id }}.quality.release_results` (
    release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
)
select
    release_id,
    rule_id,
    metric_value,
    severity,
    action,
    details
from `{{ project_id }}.quality.release_metrics`
where release_id = target_release;

set inserted_rules = (
    select count(*) from `{{ project_id }}.quality.release_results`
    where release_id = target_release
);
assert inserted_rules = 13 as 'quality evaluator must persist exactly 13 catalog rules';

commit transaction;
