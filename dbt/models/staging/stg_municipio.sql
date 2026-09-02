with bronze as (
    {{ bronze_release('municipio') }}
)

select
    {{ safe_cast('ano', 'int64') }} as ano,
    {{ normalize_municipality_id('id_municipio') }} as id_municipio,
    trim(serie) as serie,
    {{ normalize_network('rede', 'assessment_result') }} as rede,
    {{ safe_cast('taxa_alfabetizacao', 'numeric') }} as taxa_alfabetizacao,
    {{ safe_cast('media_portugues', 'numeric') }} as media_portugues,
    {% for nivel in range(9) %}
        {{ safe_cast('proporcao_aluno_nivel_' ~ nivel, 'numeric') }}
            as proporcao_aluno_nivel_{{ nivel }},
    {% endfor %}
    release_id,
    source_run_id,
    ingested_at
from bronze
