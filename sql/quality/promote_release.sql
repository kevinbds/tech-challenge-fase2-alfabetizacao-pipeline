declare candidate_release string default @release_id;
declare current_release string;
declare active_rows int64;
declare candidate_rows int64;
declare quality_rows int64;
declare required_rules_seen int64;
declare critical_failures int64;

set active_rows
= (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';

set candidate_rows = (
    select count(*)
    from `{{ project_id }}.ops.release_registry`
    where release_id = candidate_release and status = 'succeeded'
);
assert candidate_rows = 1 as 'candidate release must exist exactly once in succeeded state';

set quality_rows = (
    select count(*)
    from `{{ project_id }}.quality.release_results`
    where release_id = candidate_release
);
assert quality_rows > 0 as 'candidate release has no quality results';

set required_rules_seen = (
    select count(distinct rule_id)
    from `{{ project_id }}.quality.release_results`
    where
        release_id = candidate_release
        and rule_id in (
            'required_keys',
            'uniqueness_after_quarantine',
            'relationships',
            'gold_core_nulls',
            'optional_null_delta',
            'percentage_ranges',
            'non_negative_measurements',
            'proportions_sum',
            'repeated_evaluation_or_target_rate',
            'partition_volume',
            'pipeline_freshness',
            'identical_duplicate',
            'conflicting_duplicate'
        )
);
assert required_rules_seen = 13 as 'candidate release is missing mandatory quality rules';

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
