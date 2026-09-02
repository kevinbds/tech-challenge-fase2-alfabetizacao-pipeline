{% macro safe_cast(expression, data_type) -%}
    {% if adapter is defined %}
        {{ return(
            adapter.dispatch('safe_cast', 'alfabetizacao_medallion')(
                expression,
                data_type
            )
        ) }}
    {% endif %}
  safe_cast({{ expression }} as {{ data_type }})
{%- endmacro %}

{% macro bigquery__safe_cast(expression, data_type) -%}
    safe_cast({{ expression }} as {{ data_type }})
{%- endmacro %}

{% macro duckdb__safe_cast(expression, data_type) -%}
    try_cast({{ expression }} as {{ data_type }})
{%- endmacro %}

{% macro normalize_municipality_id(expression) -%}
    {% if adapter is defined %}
        {{ return(
            adapter.dispatch('normalize_municipality_id', 'alfabetizacao_medallion')(
                expression
            )
        ) }}
    {% endif %}
  case
    when regexp_contains(trim(cast({{ expression }} as string)), r'^[0-9]{1,7}$')
      then lpad(trim(cast({{ expression }} as string)), 7, '0')
  end
{%- endmacro %}

{% macro bigquery__normalize_municipality_id(expression) -%}
  case
    when regexp_contains(trim(cast({{ expression }} as string)), r'^[0-9]{1,7}$')
      then lpad(trim(cast({{ expression }} as string)), 7, '0')
  end
{%- endmacro %}

{% macro duckdb__normalize_municipality_id(expression) -%}
  case
    when regexp_full_match(trim(cast({{ expression }} as varchar)), '^[0-9]{1,7}$')
      then lpad(trim(cast({{ expression }} as varchar)), 7, '0')
  end
{%- endmacro %}

{% macro days_since(expression) -%}
    {% if adapter is defined %}
        {{ return(adapter.dispatch('days_since', 'alfabetizacao_medallion')(expression)) }}
    {% endif %}
  date_diff(current_date(), date({{ expression }}), day)
{%- endmacro %}

{% macro bigquery__days_since(expression) -%}
    date_diff(current_date(), date({{ expression }}), day)
{%- endmacro %}

{% macro duckdb__days_since(expression) -%}
    date_diff('day', cast({{ expression }} as date), current_date)
{%- endmacro %}
