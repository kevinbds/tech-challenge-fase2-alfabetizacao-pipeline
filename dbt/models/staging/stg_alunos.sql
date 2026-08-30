with bronze as (
    {{ bronze_release('alunos') }}
)

select
    release_id,
    source_run_id,
    ingested_at,
    safe_cast(ano as int64) as ano,
    lpad(trim(id_municipio), 7, '0') as id_municipio,
    trim(id_escola) as id_escola,
    trim(id_aluno) as id_aluno,
    trim(caderno) as caderno,
    trim(serie) as serie,
    lower(trim(rede)) as rede,
    trim(presenca) as presenca,
    trim(preenchimento_caderno) as preenchimento_caderno,
    trim(alfabetizado) as alfabetizado,
    safe_cast(proficiencia as numeric) as proficiencia,
    safe_cast(peso_aluno as numeric) as peso_aluno
from bronze
