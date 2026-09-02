{% macro bronze_release(table_name) %}
    {% if adapter is defined %}
        {{ return(adapter.dispatch('bronze_release', 'alfabetizacao_medallion')(table_name)) }}
    {% endif %}
    {{ bigquery__bronze_release(table_name) }}
{% endmacro %}

{% macro bigquery__bronze_release(table_name) %}
select
  bronze.*,
  mapping.release_id,
  mapping.source_run_id,
  mapping.ingested_at
from {{ source('bronze_restricted' if table_name == 'alunos' else 'bronze', table_name) }} as bronze
inner join {{ source('ops', 'release_files') }} as mapping
  on mapping.table_name = '{{ table_name }}'
  and mapping.file_uri = bronze._file_name
  and mapping.status = 'selected'
where mapping.release_id = '{{ var("release_id") }}'
{% endmacro %}

{% macro duckdb__bronze_release(table_name) %}
select
  bronze.* exclude (_file_name),
  mapping.release_id,
  mapping.source_run_id,
  mapping.ingested_at
from {{ source('bronze_restricted' if table_name == 'alunos' else 'bronze', table_name) }} as bronze
inner join {{ source('ops', 'release_files') }} as mapping
  on mapping.table_name = '{{ table_name }}'
  and mapping.file_uri = bronze._file_name
  and mapping.status = 'selected'
where mapping.release_id = '{{ var("release_id") }}'
{% endmacro %}
