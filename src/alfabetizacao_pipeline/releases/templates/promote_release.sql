declare candidate_release string default @release_id;
declare current_release string;
declare prior_release string;
declare active_rows int64;
declare active_registry_rows int64;
declare active_registry_state_rows int64;
declare prior_registry_rows int64;
declare prior_registry_state_rows int64;
declare candidate_rows int64;
declare candidate_active_replay_rows int64;
declare candidate_promotable_rows int64;
declare quality_rows int64;
declare required_rules_seen int64;
declare blocking_results int64;

begin transaction;
set active_rows
= (
    select count(*) from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert active_rows = 1 as 'ops.active_release must contain exactly one singleton row';

set (current_release, prior_release) = (
    select as struct
        release_id,
        prior_release_id
    from `{{ project_id }}.ops.active_release`
    where singleton_key = true
);
assert current_release is not null as 'active release pointer cannot be null';
assert (
    prior_release is null or prior_release != current_release
) as 'active release cannot reference itself as prior';

set active_registry_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = current_release
);
set active_registry_state_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = current_release and status = 'active'
);
assert (
    active_registry_rows = 1 and active_registry_state_rows = 1
) as 'active release pointer must resolve to exactly one active registry row';

set prior_registry_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = prior_release
);
set prior_registry_state_rows = (
    select count(*) from `{{ project_id }}.ops.release_registry`
    where release_id = prior_release and status = 'inactive'
);
assert (
    prior_release is null
    or (prior_registry_rows = 1 and prior_registry_state_rows = 1)
) as 'prior release pointer must resolve to exactly one inactive registry row';

set candidate_rows = (
    select count(*)
    from `{{ project_id }}.ops.release_registry`
    where release_id = candidate_release
);
set candidate_active_replay_rows = (
    select count(*)
    from `{{ project_id }}.ops.release_registry`
    where
        release_id = candidate_release
        and status = 'active'
);
set candidate_promotable_rows = (
    select count(*)
    from `{{ project_id }}.ops.release_registry` as candidate
    where
        candidate.release_id = candidate_release
        and candidate.status = 'succeeded'
        and candidate.baseline_release_id = current_release
        and (
            current_release = '__bootstrap__'
            or candidate.reference_year >= (
                select active.reference_year
                from `{{ project_id }}.ops.release_registry` as active
                where active.release_id = current_release and active.status = 'active'
            )
        )
);
assert (
    (
        candidate_release = current_release
        and candidate_rows = 1
        and candidate_active_replay_rows = 1
    )
    or (
        candidate_release != current_release
        and candidate_rows = 1
        and candidate_promotable_rows = 1
    )
) as 'candidate state or quality baseline differs';

set quality_rows = (
    select count(*)
    from `{{ project_id }}.quality.release_results`
    where release_id = candidate_release
);
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
assert (
    candidate_release = current_release
    or (quality_rows = 13 and required_rules_seen = 13)
) as 'candidate release must have exactly one result for each mandatory quality rule';

set blocking_results = (
    select count(*) from `{{ project_id }}.quality.release_results`
    where
        release_id = candidate_release
        and (
            severity = 'critical'
            or action in ('block_promotion', 'quarantine_and_block')
        )
);
assert (
    candidate_release = current_release or blocking_results = 0
) as 'candidate has blocking quality results';

update `{{ project_id }}.ops.active_release`
set
    prior_release_id = if(current_release = '__bootstrap__', null, current_release),
    release_id = candidate_release,
    promoted_at = current_timestamp()
where
    singleton_key = true
    and candidate_release != current_release
    and release_id = current_release
    and prior_release_id is not distinct from prior_release;
assert (
    candidate_release = current_release or @@row_count = 1
) as 'active release pointer changed during promotion';

update `{{ project_id }}.ops.release_registry`
set status = 'active', promoted_at = current_timestamp()
where
    candidate_release != current_release
    and release_id = candidate_release
    and status = 'succeeded';
assert (
    candidate_release = current_release or @@row_count = 1
) as 'candidate registry row changed during promotion';

update `{{ project_id }}.ops.release_registry`
set status = 'inactive'
where
    candidate_release != current_release
    and release_id = current_release
    and status = 'active';
assert (
    candidate_release = current_release or @@row_count = 1
) as 'active registry row changed during promotion';
commit transaction;
