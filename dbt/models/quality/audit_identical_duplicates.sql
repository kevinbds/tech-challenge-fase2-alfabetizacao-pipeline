{{ config(unique_key=['release_id', 'table_name', 'business_key_hash', 'source_run_id']) }}

with hashed as (
    select
        release_id,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(ano, id_municipio, rede)))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            serie, taxa_alfabetizacao, media_portugues,
            proporcao_aluno_nivel_0, proporcao_aluno_nivel_1, proporcao_aluno_nivel_2,
            proporcao_aluno_nivel_3, proporcao_aluno_nivel_4, proporcao_aluno_nivel_5,
            proporcao_aluno_nivel_6, proporcao_aluno_nivel_7, proporcao_aluno_nivel_8
        )))) as row_hash
    from {{ ref('stg_municipio') }}
    where release_id = '{{ var("release_id") }}'
),

duplicates as (
    select
        *,
        count(*) over (partition by release_id, business_key_hash) as copies,
        count(distinct row_hash) over (partition by release_id, business_key_hash) as variants
    from hashed
)

select
    release_id,
    'municipio' as table_name,
    business_key_hash,
    source_run_id,
    max(ingested_at) as detected_at,
    max(copies) as copies
from duplicates
where copies > 1 and variants = 1
group by release_id, business_key_hash, source_run_id
