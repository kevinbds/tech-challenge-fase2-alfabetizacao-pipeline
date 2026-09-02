{% macro replace_candidate_rows() %}
    {% if is_incremental() %}
        delete from {{ this }} where release_id = '{{ var("release_id") }}'
    {% endif %}
{% endmacro %}
