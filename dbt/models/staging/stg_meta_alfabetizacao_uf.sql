with bronze as (
    {{ bronze_release('meta_alfabetizacao_uf') }}
)

select
    safe_cast(ano as int64) as ano,
    upper(trim(sigla_uf)) as sigla_uf,
    lower(trim(rede)) as rede,
    safe_cast(taxa_alfabetizacao as numeric) as taxa_alfabetizacao,
    {% for ano_meta in range(2024, 2031) %}
        safe_cast(meta_alfabetizacao_{{ ano_meta }} as numeric)
            as meta_alfabetizacao_{{ ano_meta }},
    {% endfor %}
    safe_cast(percentual_participacao as numeric) as percentual_participacao,
    release_id,
    source_run_id,
    ingested_at
from bronze
