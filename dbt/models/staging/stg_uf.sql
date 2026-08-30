with bronze as (
    {{ bronze_release('uf') }}
)

select
    safe_cast(ano as int64) as ano,
    upper(trim(sigla_uf)) as sigla_uf,
    trim(serie) as serie,
    lower(trim(rede)) as rede,
    safe_cast(taxa_alfabetizacao as numeric) as taxa_alfabetizacao,
    safe_cast(media_portugues as numeric) as media_portugues,
    {% for nivel in range(9) %}
        safe_cast(proporcao_aluno_nivel_{{ nivel }} as numeric)
            as proporcao_aluno_nivel_{{ nivel }},
    {% endfor %}
    release_id,
    source_run_id,
    ingested_at
from bronze
