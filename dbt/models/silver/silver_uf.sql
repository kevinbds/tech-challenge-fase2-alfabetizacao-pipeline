{{ config(
    unique_key=['release_id', 'ano', 'sigla_uf', 'rede'],
    cluster_by=['release_id', 'sigla_uf', 'rede']
) }}

{% set payload = [
  'serie', 'taxa_alfabetizacao', 'media_portugues',
  'proporcao_aluno_nivel_0', 'proporcao_aluno_nivel_1', 'proporcao_aluno_nivel_2',
  'proporcao_aluno_nivel_3', 'proporcao_aluno_nivel_4', 'proporcao_aluno_nivel_5',
  'proporcao_aluno_nivel_6', 'proporcao_aluno_nivel_7', 'proporcao_aluno_nivel_8'
] %}
with scoped as (
    select
        *,
        date(ano, 1, 1) as ano_particao
    from {{ ref('stg_uf') }}
    where release_id = '{{ var("release_id") }}'
)
{{ deduplicate('scoped', ['release_id', 'ano', 'sigla_uf', 'rede'], payload) }}
