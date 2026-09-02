{% macro release_rule_list() -%}
  {%- for rule in [
    'required_keys', 'uniqueness_after_quarantine', 'relationships',
    'gold_core_nulls', 'optional_null_delta', 'percentage_ranges',
    'non_negative_measurements', 'proportions_sum',
    'repeated_evaluation_or_target_rate', 'partition_volume',
    'pipeline_freshness', 'identical_duplicate', 'conflicting_duplicate'
  ] -%}
        '{{ rule }}'{% if not loop.last %},{% endif %}
    {%- endfor -%}
{%- endmacro %}

{% macro validate_release_arguments(release_id) -%}
    {% if not modules.re.fullmatch('batch-[0-9]{6}-y[0-9]{4}-r[a-z0-9]{8,32}', release_id) %}
        {{ exceptions.raise_compiler_error('invalid release_id') }}
    {% endif %}
{%- endmacro %}

{% macro evaluate_release(release_id) -%}
    {% do validate_release_arguments(release_id) %}
    {{ return(
        adapter.dispatch('evaluate_release', 'alfabetizacao_medallion')(
            release_id
        )
    ) }}
{%- endmacro %}

{% macro promote_release(release_id) -%}
    {% do validate_release_arguments(release_id) %}
    {{ return(
        adapter.dispatch('promote_release', 'alfabetizacao_medallion')(
            release_id
        )
    ) }}
{%- endmacro %}
