{% macro deduplicate(relation, key_columns, payload_columns) %}
, hashed as (
  select
    *,
    to_hex(sha256(to_json_string(struct(
      {% for column in payload_columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}
    )))) as _row_hash
  from {{ relation }}
), classified as (
  select
    *,
    count(*) over (partition by {% for column in key_columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}) as _duplicate_count,
    count(distinct _row_hash) over (partition by {% for column in key_columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}) as _distinct_hashes
  from hashed
)
select * except (_row_hash, _duplicate_count, _distinct_hashes)
from classified
where _distinct_hashes = 1
qualify row_number() over (
  partition by {% for column in key_columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}
  order by ingested_at desc, source_run_id desc
) = 1
{% endmacro %}
