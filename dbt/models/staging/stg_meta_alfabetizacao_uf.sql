with bronze as (
    {{ bronze_release('meta_alfabetizacao_uf') }}
)

select
    {{ safe_cast('ano', 'int64') }} as ano,
    nullif(upper(trim(sigla_uf)), '') as sigla_uf,
    {{ normalize_network('rede', 'target') }} as rede,
    {{ safe_cast('taxa_alfabetizacao', 'numeric') }} as taxa_alfabetizacao,
    {% for ano_meta in range(2024, 2031) %}
        {{ safe_cast('meta_alfabetizacao_' ~ ano_meta, 'numeric') }}
            as meta_alfabetizacao_{{ ano_meta }},
    {% endfor %}
    {{ safe_cast('percentual_participacao', 'numeric') }} as percentual_participacao,
    release_id,
    source_run_id,
    ingested_at
from bronze
