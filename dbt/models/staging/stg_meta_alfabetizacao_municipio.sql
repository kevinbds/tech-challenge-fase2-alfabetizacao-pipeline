with bronze as (
    {{ bronze_release('meta_alfabetizacao_municipio') }}
)

select
    safe_cast(ano as int64) as ano,
    lpad(trim(id_municipio), 7, '0') as id_municipio,
    lower(trim(rede)) as rede,
    safe_cast(taxa_alfabetizacao as numeric) as taxa_alfabetizacao,
    {% for ano_meta in range(2024, 2031) %}
        safe_cast(meta_alfabetizacao_{{ ano_meta }} as numeric)
            as meta_alfabetizacao_{{ ano_meta }},
    {% endfor %}
    safe_cast(nivel_alfabetizacao as int64) as nivel_alfabetizacao,
    safe_cast(percentual_participacao as numeric) as percentual_participacao,
    release_id,
    source_run_id,
    ingested_at
from bronze
