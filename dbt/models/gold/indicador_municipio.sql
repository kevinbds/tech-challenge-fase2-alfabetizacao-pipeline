{{ config(
  materialized='incremental',
  incremental_strategy='insert_overwrite',
  unique_key=['release_id', 'ano', 'id_municipio', 'rede'],
  partition_by={'field': 'ano_particao', 'data_type': 'date', 'granularity': 'year'},
  cluster_by=['release_id', 'id_municipio', 'rede']
) }}

select
    m.release_id,
    m.ano,
    m.ano_particao,
    m.id_municipio,
    d.nome as nome_municipio,
    d.sigla_uf,
    m.rede,
    m.taxa_alfabetizacao,
    m.media_portugues,
    m.proporcao_aluno_nivel_0,
    m.proporcao_aluno_nivel_1,
    m.proporcao_aluno_nivel_2,
    m.proporcao_aluno_nivel_3,
    m.proporcao_aluno_nivel_4,
    m.proporcao_aluno_nivel_5,
    m.proporcao_aluno_nivel_6,
    m.proporcao_aluno_nivel_7,
    m.proporcao_aluno_nivel_8
from {{ ref('silver_municipio') }} as m
inner join {{ source('diretorios', 'municipio') }} as d on m.id_municipio = d.id_municipio
where m.release_id = '{{ var("release_id") }}'
{% if is_incremental() %}
and m.ano_particao in (select distinct ano_particao from {{ ref('silver_municipio') }} where release_id = '{{ var("release_id") }}')
{% endif %}
