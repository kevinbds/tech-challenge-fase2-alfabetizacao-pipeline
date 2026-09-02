{{ config(alias='evolucao_alfabetizacao') }}

with recursive active_release as (
    select release_id
    from {{ source('ops', 'active_release') }}
    where singleton_key = true
    qualify count(*) over () = 1
),

release_chain as (
    select
        registry.release_id,
        registry.reference_year,
        registry.baseline_release_id,
        0 as chain_level
    from active_release as active
    inner join {{ source('ops', 'release_registry') }} as registry
        on active.release_id = registry.release_id and registry.status = 'active'
    union all
    select
        registry.release_id,
        registry.reference_year,
        registry.baseline_release_id,
        ancestor.chain_level + 1 as chain_level
    from release_chain as ancestor
    inner join {{ source('ops', 'release_registry') }} as registry
        on ancestor.baseline_release_id = registry.release_id
    where registry.release_id != '__bootstrap__'
),

published_releases as (
    select release_id from release_chain
    qualify row_number() over (
        partition by reference_year order by chain_level
    ) = 1
)

select
    candidate.release_id,
    candidate.ano,
    candidate.ano_particao,
    candidate.id_municipio,
    candidate.nome_municipio,
    candidate.sigla_uf,
    candidate.rede,
    candidate.taxa_alfabetizacao,
    candidate.media_portugues,
    candidate.proporcao_aluno_nivel_0,
    candidate.proporcao_aluno_nivel_1,
    candidate.proporcao_aluno_nivel_2,
    candidate.proporcao_aluno_nivel_3,
    candidate.proporcao_aluno_nivel_4,
    candidate.proporcao_aluno_nivel_5,
    candidate.proporcao_aluno_nivel_6,
    candidate.proporcao_aluno_nivel_7,
    candidate.proporcao_aluno_nivel_8,
    candidate.taxa_ano_anterior,
    candidate.variacao_pp
from {{ ref('evolucao_alfabetizacao') }} as candidate
inner join published_releases as published
    on candidate.release_id = published.release_id
