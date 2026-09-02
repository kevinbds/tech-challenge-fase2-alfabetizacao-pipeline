{% macro bigquery__evaluate_release(release_id) -%}
    {% set sql %}
  begin transaction;
  assert (select count(*) from {{ source('ops', 'release_registry') }}
    where release_id='{{ release_id }}' and status='succeeded'
    and baseline_release_id is not null)=1
    as 'candidate state or baseline differs';
  assert (select count(*) from {{ ref('release_metrics') }}
    where release_id='{{ release_id }}')=13 as 'release metrics must contain 13 rules';
  assert (select count(distinct rule_id) from {{ ref('release_metrics') }}
    where release_id='{{ release_id }}' and rule_id in ({{ release_rule_list() }}))=13
    as 'release metrics rule catalog differs';
  delete from {{ source('quality', 'release_results') }} where release_id='{{ release_id }}';
  insert into {{ source('quality', 'release_results') }}
    (release_id,rule_id,metric_value,severity,action,details,evaluated_at)
  select release_id,rule_id,metric_value,severity,action,details,current_timestamp()
  from {{ ref('release_metrics') }} where release_id='{{ release_id }}';
  commit transaction;
  {% endset %}
    {% do run_query(sql) %}
{%- endmacro %}

{% macro duckdb__evaluate_release(release_id) -%}
    {% do run_query('begin transaction') %}
    {% set candidate_sql %}
        select count(*)
        from ops.release_registry
        where release_id = '{{ release_id }}'
            and status = 'succeeded'
            and baseline_release_id is not null
    {% endset %}
    {% set candidate = run_query(candidate_sql) %}
    {% if candidate.columns[0].values()[0] != 1 %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('candidate state or baseline differs') }}
    {% endif %}
    {% set metrics_sql %}
        select
            count(*),
            count(distinct rule_id),
            count(*) filter (where rule_id not in ({{ release_rule_list() }}))
        from quality.release_metrics
        where release_id = '{{ release_id }}'
    {% endset %}
    {% set metrics = run_query(metrics_sql) %}
    {% if (
        metrics.columns[0].values()[0] != 13
        or metrics.columns[1].values()[0] != 13
        or metrics.columns[2].values()[0] != 0
    ) %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('release metrics catalog differs') }}
    {% endif %}
    {% set delete_sql %}
        delete from quality.release_results where release_id = '{{ release_id }}'
    {% endset %}
    {% do run_query(delete_sql) %}
    {% set insert_sql %}
        insert into quality.release_results
        select *, current_timestamp
        from quality.release_metrics
        where release_id = '{{ release_id }}'
    {% endset %}
    {% do run_query(insert_sql) %}
    {% set audit_sql %}
        select
            count(*),
            count(distinct rule_id),
            count(*) filter (where rule_id not in ({{ release_rule_list() }}))
        from quality.release_results
        where release_id = '{{ release_id }}'
    {% endset %}
    {% set audit = run_query(audit_sql) %}
    {% if (
        audit.columns[0].values()[0] != 13
        or audit.columns[1].values()[0] != 13
        or audit.columns[2].values()[0] != 0
    ) %}
        {% do run_query('rollback') %}
        {{ exceptions.raise_compiler_error('release quality catalog differs') }}
    {% endif %}
    {% do run_query('commit') %}
{%- endmacro %}
