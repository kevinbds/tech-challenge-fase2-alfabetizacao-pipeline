declare target_release string default @release_id;

with current_metrics as (
    select
        target_release as release_id,
        @required_key_null_rate as required_key_null_rate,
        @relationship_rate as relationship_rate,
        @optional_null_delta_pp as optional_null_delta_pp,
        @repeated_rate_percent as repeated_rate_percent,
        @current_row_count as current_row_count,
        @previous_row_count as previous_row_count,
        @days_since_success as days_since_success
),

evaluated as (
    select
        release_id,
        'required_keys' as rule_id,
        required_key_null_rate as metric_value,
        if(required_key_null_rate = 0, 'pass', 'critical') as severity,
        if(required_key_null_rate = 0, 'promote', 'quarantine_and_block') as action
    from current_metrics
    union all
    select
        release_id,
        'relationships' as rule_id,
        relationship_rate as metric_value,
        if(relationship_rate = 100, 'pass', 'critical') as severity,
        if(relationship_rate = 100, 'promote', 'quarantine_and_block') as action
    from current_metrics
    union all
    select
        release_id,
        'optional_null_delta' as rule_id,
        optional_null_delta_pp as metric_value,
        if(optional_null_delta_pp > 5, 'warning', 'pass') as severity,
        if(optional_null_delta_pp > 5, 'continue_with_alert', 'promote') as action
    from current_metrics
    union all
    select
        release_id,
        'repeated_evaluation_or_target_rate' as rule_id,
        repeated_rate_percent as metric_value,
        case
            when repeated_rate_percent <= 0.01 then 'pass'
            when repeated_rate_percent <= 0.50 then 'warning' else 'critical'
        end as severity,
        case
            when repeated_rate_percent <= 0.01 then 'promote'
            when repeated_rate_percent <= 0.50 then 'continue_with_alert'
            else 'quarantine_and_block'
        end as action
    from current_metrics
    union all
    select
        release_id,
        'partition_volume' as rule_id,
        if(
            previous_row_count = 0,
            0,
            100 * (previous_row_count - current_row_count) / previous_row_count
        ) as metric_value,
        case
            when
                current_row_count = 0 or current_row_count < previous_row_count * 0.5
                then 'critical'
            when
                abs(current_row_count - previous_row_count) > previous_row_count * 0.2
                then 'warning'
            else 'pass'
        end as severity,
        case
            when
                current_row_count = 0 or current_row_count < previous_row_count * 0.5
                then 'block_promotion'
            when
                abs(current_row_count - previous_row_count) > previous_row_count * 0.2
                then 'continue_with_alert'
            else 'promote'
        end as action
    from current_metrics
    union all
    select
        release_id,
        'pipeline_freshness' as rule_id,
        days_since_success as metric_value,
        if(days_since_success <= 35, 'pass', 'critical') as severity,
        if(days_since_success <= 35, 'promote', 'block_promotion') as action
    from current_metrics
)

select * from evaluated;
