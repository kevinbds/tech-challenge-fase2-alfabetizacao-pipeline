{% macro ref(model_name) %}`local.alfabetizacao.{{ model_name }}`{% endmacro %}
{% macro source(source_name, table_name) %}`local.{{ source_name }}.{{ table_name }}`{% endmacro %}
{% macro var(name) %}local-release{% endmacro %}
{% macro is_incremental() %}true{% endmacro %}
