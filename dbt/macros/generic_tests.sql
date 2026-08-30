{% test unique_key(model, columns) %}
select {% for column in columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}
from {{ model }}
group by {% for column in columns %}{{ column }}{% if not loop.last %}, {% endif %}{% endfor %}
having count(*) > 1
{% endtest %}

{% test accepted_numeric_range(model, column_name, minimum, maximum) %}
select * from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ minimum }} or {{ column_name }} > {{ maximum }})
{% endtest %}

{% test proportions_total(model, columns, minimum=99.5, maximum=100.5) %}
select * from {{ model }}
where ({% for column in columns %}coalesce({{ column }}, 0){% if not loop.last %} + {% endif %}{% endfor %})
  not between {{ minimum }} and {{ maximum }}
{% endtest %}

{% test composite_relationship(model, to, columns) %}
select child.*
from {{ model }} as child
left join {{ to }} as parent
  on {% for column in columns %}child.{{ column }} = parent.{{ column }}{% if not loop.last %} and {% endif %}{% endfor %}
where parent.{{ columns[0] }} is null
{% endtest %}
