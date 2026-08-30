{% macro bronze_release(table_name) %}
select
  bronze.* except (_file_name),
  mapping.release_id,
  mapping.source_run_id,
  mapping.ingested_at
from {{ source('bronze', table_name) }} as bronze
inner join {{ source('ops', 'release_files') }} as mapping
  on mapping.table_name = '{{ table_name }}'
  and mapping.file_uri = bronze._file_name
  and mapping.status = 'selected'
where mapping.release_id = '{{ var("release_id") }}'
{% endmacro %}
