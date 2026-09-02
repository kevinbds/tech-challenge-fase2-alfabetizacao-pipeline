with bronze as (
    {{ bronze_release('alunos') }}
)

select
    release_id,
    source_run_id,
    ingested_at,
    {{ safe_cast('ano', 'int64') }} as ano,
    {{ normalize_municipality_id('id_municipio') }} as id_municipio,
    nullif(trim(id_escola), '') as id_escola,
    nullif(trim(id_aluno), '') as id_aluno,
    trim(caderno) as caderno,
    trim(serie) as serie,
    {{ normalize_network('rede', 'student_dependency') }} as rede,
    trim(presenca) as presenca,
    trim(preenchimento_caderno) as preenchimento_caderno,
    trim(alfabetizado) as alfabetizado,
    {{ safe_cast('proficiencia', 'numeric') }} as proficiencia,
    {{ safe_cast('peso_aluno', 'numeric') }} as peso_aluno
from bronze
