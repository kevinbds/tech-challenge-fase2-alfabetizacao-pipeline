declare target_release string default @release_id;
declare required_key_null_rate float64 default @required_key_null_rate;
declare duplicate_key_rate float64 default @duplicate_key_rate;
declare relationship_rate float64 default @relationship_rate;
declare gold_core_null_rate float64 default @gold_core_null_rate;
declare optional_null_delta_pp float64 default @optional_null_delta_pp;
declare out_of_range_rows int64 default @out_of_range_rows;
declare negative_rows int64 default @negative_rows;
declare invalid_proportion_rows int64 default @invalid_proportion_rows;
declare repeated_rate_percent float64 default @repeated_rate_percent;
declare current_row_count int64 default @current_row_count;
declare previous_row_count int64 default @previous_row_count;
declare days_since_success int64 default @days_since_success;
declare identical_copies int64 default @identical_copies;
declare identical_payload_hashes int64 default @identical_payload_hashes;
declare conflicting_payload_variants int64 default @conflicting_payload_variants;

begin transaction;

delete from `{{ project_id }}.quality.release_results`
where release_id = target_release;

insert into `{{ project_id }}.quality.release_results` (
    release_id,
    rule_id,
    metric_value,
    severity,
    action
)
with evaluated as (
    select
        target_release as release_id,
        'required_keys' as rule_id,
        required_key_null_rate as metric_value,
        if(required_key_null_rate = 0, 'pass', 'critical') as severity,
        if(required_key_null_rate = 0, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'uniqueness_after_quarantine' as rule_id,
        duplicate_key_rate as metric_value,
        if(duplicate_key_rate = 0, 'pass', 'critical') as severity,
        if(duplicate_key_rate = 0, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'relationships' as rule_id,
        relationship_rate as metric_value,
        if(relationship_rate = 100, 'pass', 'critical') as severity,
        if(relationship_rate = 100, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'gold_core_nulls' as rule_id,
        gold_core_null_rate as metric_value,
        if(gold_core_null_rate = 0, 'pass', 'critical') as severity,
        if(gold_core_null_rate = 0, 'promote', 'block_promotion') as action
    union all
    select
        target_release as release_id,
        'optional_null_delta' as rule_id,
        optional_null_delta_pp as metric_value,
        if(optional_null_delta_pp <= 5, 'pass', 'warning') as severity,
        if(optional_null_delta_pp <= 5, 'promote', 'continue_with_alert') as action
    union all
    select
        target_release as release_id,
        'percentage_ranges' as rule_id,
        out_of_range_rows as metric_value,
        if(out_of_range_rows = 0, 'pass', 'critical') as severity,
        if(out_of_range_rows = 0, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'non_negative_measurements' as rule_id,
        negative_rows as metric_value,
        if(negative_rows = 0, 'pass', 'critical') as severity,
        if(negative_rows = 0, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'proportions_sum' as rule_id,
        invalid_proportion_rows as metric_value,
        if(invalid_proportion_rows = 0, 'pass', 'critical') as severity,
        if(invalid_proportion_rows = 0, 'promote', 'quarantine_and_block') as action
    union all
    select
        target_release as release_id,
        'repeated_evaluation_or_target_rate' as rule_id,
        repeated_rate_percent as metric_value,
        case
            when repeated_rate_percent <= 0.01 then 'pass'
            when repeated_rate_percent <= 0.50 then 'warning'
            else 'critical'
        end as severity,
        case
            when repeated_rate_percent <= 0.01 then 'promote'
            when repeated_rate_percent <= 0.50 then 'continue_with_alert'
            else 'quarantine_and_block'
        end as action
    union all
    select
        target_release as release_id,
        'partition_volume' as rule_id,
        if(
            previous_row_count = 0,
            0,
            100 * (previous_row_count - current_row_count) / previous_row_count
        ) as metric_value,
        case
            when current_row_count = 0 or current_row_count < previous_row_count * 0.5
                then 'critical'
            when abs(current_row_count - previous_row_count) > previous_row_count * 0.2
                then 'warning'
            else 'pass'
        end as severity,
        case
            when current_row_count = 0 or current_row_count < previous_row_count * 0.5
                then 'block_promotion'
            when abs(current_row_count - previous_row_count) > previous_row_count * 0.2
                then 'continue_with_alert'
            else 'promote'
        end as action
    union all
    select
        target_release as release_id,
        'pipeline_freshness' as rule_id,
        days_since_success as metric_value,
        if(days_since_success <= 35, 'pass', 'critical') as severity,
        if(days_since_success <= 35, 'promote', 'block_promotion') as action
    union all
    select
        target_release as release_id,
        'identical_duplicate' as rule_id,
        identical_copies as metric_value,
        if(
            identical_copies > 1 and identical_payload_hashes = 1, 'warning', 'pass'
        ) as severity,
        if(
            identical_copies > 1 and identical_payload_hashes = 1,
            'deduplicate_and_alert',
            'promote'
        ) as action
    union all
    select
        target_release as release_id,
        'conflicting_duplicate' as rule_id,
        conflicting_payload_variants as metric_value,
        if(conflicting_payload_variants = 1, 'pass', 'critical') as severity,
        if(conflicting_payload_variants = 1, 'promote', 'quarantine_and_block') as action
)

select
    release_id,
    rule_id,
    metric_value,
    severity,
    action
from evaluated;
assert @@row_count = 13 as 'quality evaluation must persist all mandatory rules';

commit transaction;
