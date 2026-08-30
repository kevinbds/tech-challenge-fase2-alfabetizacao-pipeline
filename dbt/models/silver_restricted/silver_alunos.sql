{{ config(unique_key=['release_id', 'ano', 'id_municipio', 'id_escola', 'id_aluno']) }}

{% set payload = [
  'caderno', 'serie', 'rede', 'presenca', 'preenchimento_caderno',
  'alfabetizado', 'proficiencia', 'peso_aluno'
] %}
with scoped as (
    select
        *,
        date(ano, 1, 1) as ano_particao
    from {{ ref('stg_alunos') }}
    where release_id = '{{ var("release_id") }}'
)
{{ deduplicate('scoped', ['release_id', 'ano', 'id_municipio', 'id_escola', 'id_aluno'], payload) }}
