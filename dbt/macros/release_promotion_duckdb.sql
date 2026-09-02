{% macro duckdb__promote_release(release_id) -%}
    {% set singleton_sql %}
        select count(*) from ops.active_release where singleton_key
    {% endset %}
    {% set singleton = run_query(singleton_sql) %}
    {% if singleton.columns[0].values()[0] != 1 %}
        {{ exceptions.raise_compiler_error('active release singleton is invalid') }}
    {% endif %}
    {% set current = run_query(
        "select release_id, prior_release_id from ops.active_release where singleton_key"
    ) %}
    {% set current_id = current.columns[0].values()[0] %}
    {% set prior_id = current.columns[1].values()[0] %}
    {% if current_id is none %}
        {{ exceptions.raise_compiler_error('active release pointer cannot be null') }}
    {% endif %}
    {% if prior_id == current_id %}
        {{ exceptions.raise_compiler_error('active release cannot reference itself as prior') }}
    {% endif %}
    {% set current_registry_sql %}
        select
            count(*),
            count(*) filter (where status = 'active')
        from ops.release_registry
        where release_id = '{{ current_id }}'
    {% endset %}
    {% set current_registry = run_query(current_registry_sql) %}
    {% if (
        current_registry.columns[0].values()[0] != 1
        or current_registry.columns[1].values()[0] != 1
    ) %}
        {{ exceptions.raise_compiler_error(
            'active release pointer must resolve to exactly one active registry row'
        ) }}
    {% endif %}
    {% if prior_id is not none %}
        {% set prior_registry_sql %}
            select
                count(*),
                count(*) filter (where status = 'inactive')
            from ops.release_registry
            where release_id = '{{ prior_id }}'
        {% endset %}
        {% set prior_registry = run_query(prior_registry_sql) %}
        {% if (
            prior_registry.columns[0].values()[0] != 1
            or prior_registry.columns[1].values()[0] != 1
        ) %}
            {{ exceptions.raise_compiler_error(
                'prior release pointer must resolve to exactly one inactive registry row'
            ) }}
        {% endif %}
    {% endif %}
    {% set candidate_rows_sql %}
        select count(*)
        from ops.release_registry
        where release_id = '{{ release_id }}'
    {% endset %}
    {% set candidate_rows = run_query(candidate_rows_sql) %}
    {% if candidate_rows.columns[0].values()[0] != 1 %}
        {{ exceptions.raise_compiler_error(
            'candidate release must resolve to exactly one registry row'
        ) }}
    {% endif %}
    {% set active_replay_sql %}
        select count(*)
        from ops.release_registry as registry
        inner join ops.active_release as active
            on active.singleton_key and active.release_id = registry.release_id
        where registry.release_id = '{{ release_id }}'
            and registry.status = 'active'
    {% endset %}
    {% set active_replay = run_query(active_replay_sql) %}
    {% if active_replay.columns[0].values()[0] == 1 %}
        {{ return(none) }}
    {% endif %}
    {% set candidate_sql %}
        select count(*)
        from ops.release_registry
        where release_id = '{{ release_id }}'
            and status = 'succeeded'
            and baseline_release_id = '{{ current_id }}'
            and (
                '{{ current_id }}' = '__bootstrap__'
                or reference_year >= (
                    select reference_year
                    from ops.release_registry
                    where release_id = '{{ current_id }}' and status = 'active'
                )
            )
    {% endset %}
    {% set candidate = run_query(candidate_sql) %}
    {% if candidate.columns[0].values()[0] != 1 %}
        {{ exceptions.raise_compiler_error('candidate state or quality baseline differs') }}
    {% endif %}
    {% set quality_sql %}
        select
            count(*),
            count(distinct rule_id),
            count(*) filter (where rule_id not in ({{ release_rule_list() }})),
            count(*) filter (
                where severity = 'critical'
                    or action in ('block_promotion', 'quarantine_and_block')
            )
        from quality.release_results
        where release_id = '{{ release_id }}'
    {% endset %}
    {% set quality = run_query(quality_sql) %}
    {% if (
        quality.columns[0].values()[0] != 13
        or quality.columns[1].values()[0] != 13
        or quality.columns[2].values()[0] != 0
    ) %}
        {{ exceptions.raise_compiler_error('release quality catalog differs') }}
    {% elif quality.columns[3].values()[0] != 0 %}
        {{ exceptions.raise_compiler_error('candidate has blocking quality results') }}
    {% endif %}
    {% set prior_value = "null" if current_id == '__bootstrap__' else "'" ~ current_id ~ "'" %}
    {% set current_prior_value = "null" if prior_id is none else "'" ~ prior_id ~ "'" %}
    {% do run_query('begin transaction') %}
    {% set pointer_update_sql %}
        update ops.active_release
        set
            release_id = '{{ release_id }}',
            prior_release_id = {{ prior_value }},
            promoted_at = current_timestamp
        where singleton_key
            and release_id = '{{ current_id }}'
            and prior_release_id is not distinct from {{ current_prior_value }}
        returning release_id
    {% endset %}
    {% set pointer_update = run_query(pointer_update_sql) %}
    {% if pointer_update.rows | length != 1 %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('active release changed during promotion') }}
    {% endif %}
    {% set candidate_update_sql %}
        update ops.release_registry
        set status = 'active', promoted_at = current_timestamp
        where release_id = '{{ release_id }}'
            and status = 'succeeded'
        returning release_id
    {% endset %}
    {% set candidate_update = run_query(candidate_update_sql) %}
    {% if candidate_update.rows | length != 1 %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('candidate changed during promotion') }}
    {% endif %}
    {% set prior_update_sql %}
        update ops.release_registry
        set status = 'inactive'
        where release_id = '{{ current_id }}' and status = 'active'
        returning release_id
    {% endset %}
    {% set prior_update = run_query(prior_update_sql) %}
    {% if prior_update.rows | length != 1 %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('prior release changed during promotion') }}
    {% endif %}
    {% set final_state_sql %}
        select
            (select count(*)
             from ops.active_release
             where singleton_key
                 and release_id = '{{ release_id }}'
                 and prior_release_id is not distinct from {{ prior_value }}),
            (select count(*)
             from ops.release_registry
             where release_id = '{{ release_id }}' and status = 'active'),
            (select count(*)
             from ops.release_registry
             where release_id = '{{ current_id }}' and status = 'inactive')
    {% endset %}
    {% set final_state = run_query(final_state_sql) %}
    {% if (
        final_state.columns[0].values()[0] != 1
        or final_state.columns[1].values()[0] != 1
        or final_state.columns[2].values()[0] != 1
    ) %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('promotion final state is inconsistent') }}
    {% endif %}
    {% do run_query('commit') %}
{%- endmacro %}
