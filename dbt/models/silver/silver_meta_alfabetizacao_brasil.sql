{{ config(unique_key=['release_id', 'ano', 'rede'], cluster_by=['release_id', 'rede']) }}

{% set payload = [
  'taxa_alfabetizacao', 'meta_alfabetizacao_2024', 'meta_alfabetizacao_2025',
  'meta_alfabetizacao_2026', 'meta_alfabetizacao_2027', 'meta_alfabetizacao_2028',
  'meta_alfabetizacao_2029', 'meta_alfabetizacao_2030', 'percentual_participacao'
] %}
with scoped as (
    select
        *,
        date(ano, 1, 1) as ano_particao
    from {{ ref('stg_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
)
{{ deduplicate('scoped', ['release_id', 'ano', 'rede'], payload) }}
