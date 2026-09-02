{{ config(alias='comparativo_meta_resultado') }}

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
    select
        release_id,
        reference_year,
        chain_level
    from release_chain
    qualify row_number() over (
        partition by reference_year order by chain_level
    ) = 1
)

select
    candidate.release_id,
    candidate.ano_meta,
    candidate.ano_resultado,
    candidate.ano_particao,
    candidate.nivel_geografico,
    candidate.id_geografia,
    candidate.nome_geografia,
    candidate.rede,
    candidate.ano_referencia,
    candidate.meta_alfabetizacao,
    candidate.taxa_resultado,
    candidate.gap_pp,
    candidate.status_meta
from {{ ref('comparativo_meta_resultado') }} as candidate
inner join published_releases as published
    on candidate.release_id = published.release_id
where published.reference_year <= candidate.ano_meta
qualify row_number() over (
    partition by
        candidate.ano_meta,
        candidate.nivel_geografico,
        candidate.id_geografia,
        candidate.rede
    order by published.reference_year desc, published.chain_level asc
) = 1
