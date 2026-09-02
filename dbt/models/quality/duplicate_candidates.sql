{{ config(materialized='table', schema='quality', alias='duplicate_candidates') }}

with candidates as (
    select
        release_id,
        'municipio' as table_name,
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
    union all
    select
        release_id,
        'uf' as table_name,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(ano, sigla_uf, rede)))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            serie, taxa_alfabetizacao, media_portugues,
            proporcao_aluno_nivel_0, proporcao_aluno_nivel_1, proporcao_aluno_nivel_2,
            proporcao_aluno_nivel_3, proporcao_aluno_nivel_4, proporcao_aluno_nivel_5,
            proporcao_aluno_nivel_6, proporcao_aluno_nivel_7, proporcao_aluno_nivel_8
        )))) as row_hash
    from {{ ref('stg_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        'meta_municipio' as table_name,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(ano, id_municipio, rede)))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            taxa_alfabetizacao, meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027, meta_alfabetizacao_2028,
            meta_alfabetizacao_2029, meta_alfabetizacao_2030, nivel_alfabetizacao,
            percentual_participacao
        )))) as row_hash
    from {{ ref('stg_meta_alfabetizacao_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        'meta_uf' as table_name,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(ano, sigla_uf, rede)))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            taxa_alfabetizacao, meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027, meta_alfabetizacao_2028,
            meta_alfabetizacao_2029, meta_alfabetizacao_2030, percentual_participacao
        )))) as row_hash
    from {{ ref('stg_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        'meta_brasil' as table_name,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(ano, rede)))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            taxa_alfabetizacao, meta_alfabetizacao_2024, meta_alfabetizacao_2025,
            meta_alfabetizacao_2026, meta_alfabetizacao_2027, meta_alfabetizacao_2028,
            meta_alfabetizacao_2029, meta_alfabetizacao_2030, percentual_participacao
        )))) as row_hash
    from {{ ref('stg_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        release_id,
        'alunos' as table_name,
        source_run_id,
        ingested_at,
        to_hex(sha256(to_json_string(struct(
            ano, id_municipio, id_escola, id_aluno
        )))) as business_key_hash,
        to_hex(sha256(to_json_string(struct(
            caderno, serie, rede, presenca, preenchimento_caderno, alfabetizado,
            proficiencia, peso_aluno
        )))) as row_hash
    from {{ ref('stg_alunos') }}
    where release_id = '{{ var("release_id") }}'
)

select * from candidates
