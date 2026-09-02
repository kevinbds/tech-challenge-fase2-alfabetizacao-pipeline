{% macro normalize_network(expression, source_domain) -%}
  case
    {% if source_domain == 'assessment_result' %}
      when lower(trim({{ expression }})) in ('0', 'total') then 'total'
      when lower(trim({{ expression }})) in ('2', 'estadual') then 'estadual'
      when lower(trim({{ expression }})) in ('3', 'municipal') then 'municipal'
      when lower(trim({{ expression }})) in ('5', 'publica', 'pública') then 'publica'
    {% elif source_domain == 'student_dependency' %}
      when lower(trim({{ expression }})) in ('1', 'federal') then 'federal'
      when lower(trim({{ expression }})) in ('2', 'estadual') then 'estadual'
      when lower(trim({{ expression }})) in ('3', 'municipal') then 'municipal'
      when lower(trim({{ expression }})) in ('4', 'privada') then 'privada'
    {% elif source_domain == 'target' %}
      when lower(trim({{ expression }})) = 'total' then 'total'
      when lower(trim({{ expression }})) = 'federal' then 'federal'
      when lower(trim({{ expression }})) = 'estadual' then 'estadual'
      when lower(trim({{ expression }})) = 'municipal' then 'municipal'
      when lower(trim({{ expression }})) in ('publica', 'pública') then 'publica'
      when lower(trim({{ expression }})) = 'privada' then 'privada'
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown network source domain: ' ~ source_domain) }}
    {% endif %}
  end
{%- endmacro %}
