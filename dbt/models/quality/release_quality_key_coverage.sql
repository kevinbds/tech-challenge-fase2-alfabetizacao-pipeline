{{ config(materialized='ephemeral') }}

with silver_keys as (
    select
        'municipio' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        cast(null as string) as extra_id
    from {{ ref('silver_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'uf' as table_name,
        ano,
        sigla_uf as geography_id,
        rede,
        cast(null as string) as extra_id
    from {{ ref('silver_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_municipio' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        cast(null as string) as extra_id
    from {{ ref('silver_meta_alfabetizacao_municipio') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_uf' as table_name,
        ano,
        sigla_uf as geography_id,
        rede,
        cast(null as string) as extra_id
    from {{ ref('silver_meta_alfabetizacao_uf') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'meta_brasil' as table_name,
        ano,
        'BRASIL' as geography_id,
        rede,
        cast(null as string) as extra_id
    from {{ ref('silver_meta_alfabetizacao_brasil') }}
    where release_id = '{{ var("release_id") }}'
    union all
    select
        'alunos' as table_name,
        ano,
        id_municipio as geography_id,
        rede,
        id_escola || '|' || id_aluno as extra_id
    from {{ ref('silver_alunos') }}
    where release_id = '{{ var("release_id") }}'
),

key_counts as (
    select
        count(*) as row_count,
        countif(
            ano is null or geography_id is null or geography_id = ''
            or rede is null or rede = ''
            or (table_name = 'alunos' and (extra_id is null or extra_id = '|'))
        ) as null_keys,
        count(distinct table_name) as covered_silver_tables
    from silver_keys
),

duplicate_summary as (
    select coalesce(sum(copies - 1), 0) as duplicate_rows
    from (
        select count(*) as copies
        from silver_keys
        group by table_name, ano, geography_id, rede, extra_id
    ) as repeated_keys
),

expected_sources as (
    select 'uf' as table_name
    union all
    select 'meta_alfabetizacao_brasil' as table_name
    union all
    select 'meta_alfabetizacao_uf' as table_name
    union all
    select 'meta_alfabetizacao_municipio' as table_name
    union all
    select 'municipio' as table_name
    union all
    select 'alunos' as table_name
),

source_totals as (
    select
        table_name,
        sum(row_count) as row_count
    from {{ source('ops', 'release_files') }}
    where release_id = '{{ var("release_id") }}' and status = 'selected'
    group by table_name
),

source_coverage as (
    select
        countif(total.table_name is not null) as covered_sources,
        countif(total.row_count is null or total.row_count <= 0) as empty_sources,
        (
            select count(*) from source_totals as unexpected
            where unexpected.table_name not in (
                select expected.table_name from expected_sources as expected
            )
        ) as unexpected_sources
    from expected_sources as expected
    left join source_totals as total on expected.table_name = total.table_name
)

select
    key_counts.covered_silver_tables,
    source_coverage.covered_sources,
    source_coverage.empty_sources,
    source_coverage.unexpected_sources,
    100.0 * key_counts.null_keys / nullif(key_counts.row_count, 0) as null_rate,
    100.0 * duplicate_summary.duplicate_rows
    / nullif(key_counts.row_count, 0) as duplicate_rate
from key_counts
cross join duplicate_summary
cross join source_coverage
