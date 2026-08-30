create table active_release as
select
    true as singleton_key,
    cast('release-a' as varchar) as release_id,
    timestamp '2024-06-01 00:00:00' as promoted_at;

create table silver_municipio (
    release_id string, ano int64, id_municipio string, rede string,
    taxa_alfabetizacao double
);
insert into silver_municipio values
('release-a', 2023, '3304557', 'estadual', 70.0),
('release-a', 2023, '3550308', 'municipal', 60.0),
('release-a', 2024, '3304557', 'estadual', 73.0),
('release-a', 2024, '3550308', 'municipal', 68.0),
('release-old', 2024, '3550308', 'municipal', 10.0);

create table diretorio_municipio (
    id_municipio string, nome_municipio string, sigla_uf string
);
insert into diretorio_municipio values
('3304557', 'Rio de Janeiro', 'RJ'),
('3550308', 'São Paulo', 'SP');

create table silver_meta_municipio (
    release_id string, ano_referencia int64, id_municipio string, rede string,
    meta_alfabetizacao_2024 double, meta_alfabetizacao_2025 double
);
insert into silver_meta_municipio values
('release-a', 2023, '3304557', 'estadual', 72.0, 75.0),
('release-a', 2023, '3550308', 'municipal', 65.0, 70.0),
('release-a', 2024, '3550308', 'municipal', 67.0, null);

create table stream_events (
    event_id string, id_municipio string, rede string, ano int64,
    taxa_alfabetizacao double, simulation boolean,
    event_time timestamp, publish_time timestamp
);
insert into stream_events values
(
    'event-old', '3550308', 'municipal', 2024, 66.0, true,
    timestamp '2024-05-30 12:00:00', timestamp '2024-05-30 12:00:01'
),
(
    'event-a', '3550308', 'municipal', 2024, 71.0, true,
    timestamp '2024-06-02 12:00:00', timestamp '2024-06-02 12:00:01'
),
(
    'event-z', '3550308', 'municipal', 2024, 72.0, true,
    timestamp '2024-06-02 12:00:00', timestamp '2024-06-02 12:00:02'
);

create table gold_indicador_municipio as
select
    m.ano,
    m.id_municipio,
    m.rede,
    m.taxa_alfabetizacao,
    d.nome_municipio,
    d.sigla_uf,
    m.release_id
from silver_municipio as m
inner join active_release as ar on ar.singleton_key and m.release_id = ar.release_id
inner join diretorio_municipio as d on m.id_municipio = d.id_municipio;

create table gold_comparativo_meta_resultado as
with metas as (
    select
        release_id,
        ano_referencia,
        id_municipio,
        rede,
        ano_meta_nome,
        meta_alfabetizacao
    from silver_meta_municipio
    unpivot include nulls (
        meta_alfabetizacao for ano_meta_nome in (
            meta_alfabetizacao_2024, meta_alfabetizacao_2025
        )
    )
),

metas_tipadas as (
    select
        release_id,
        ano_referencia,
        id_municipio,
        rede,
        meta_alfabetizacao,
        cast(right(ano_meta_nome, 4) as integer) as ano_meta
    from metas
),

escolhidas as (
    select
        *,
        row_number() over (
            partition by release_id, ano_meta, id_municipio, rede
            order by ano_referencia desc
        ) as ordem
    from metas_tipadas
    where ano_referencia <= ano_meta and meta_alfabetizacao is not null
)

select
    i.ano as ano_resultado,
    cast('municipio' as varchar) as nivel_geografico,
    i.id_municipio as id_geografia,
    i.rede,
    e.ano_referencia,
    e.meta_alfabetizacao,
    i.taxa_alfabetizacao as taxa_resultado,
    i.taxa_alfabetizacao - e.meta_alfabetizacao as gap_pp,
    case
        when i.taxa_alfabetizacao >= e.meta_alfabetizacao
            then 'atingida'
        else 'nao_atingida'
    end as status_meta,
    i.release_id
from gold_indicador_municipio as i
inner join escolhidas
    as e on i.release_id = e.release_id
and i.ano = e.ano_meta and i.id_municipio = e.id_municipio
and i.rede = e.rede and e.ordem = 1;

create table gold_evolucao_alfabetizacao as
with base as (
    select
        release_id,
        ano,
        id_municipio,
        rede,
        taxa_alfabetizacao,
        nome_municipio,
        sigla_uf,
        lag(taxa_alfabetizacao) over (
            partition by id_municipio, rede order by ano
        ) as taxa_ano_anterior
    from gold_indicador_municipio
)

select
    release_id,
    ano,
    id_municipio,
    rede,
    taxa_alfabetizacao,
    nome_municipio,
    sigla_uf,
    taxa_ano_anterior,
    taxa_alfabetizacao - taxa_ano_anterior as variacao_pp
from base;

create table gold_indicador_atual_hibrido as
with batch_atual as (
    select * from gold_indicador_municipio
    qualify row_number() over (
        partition by id_municipio, rede order by ano desc
    ) = 1
),

stream_atual as (
    select s.* from stream_events as s
    inner join active_release as ar on ar.singleton_key
    where s.simulation and s.event_time > ar.promoted_at
    qualify row_number() over (
        partition by s.id_municipio, s.rede
        order by s.event_time desc, s.publish_time desc, s.event_id desc
    ) = 1
)

select
    b.id_municipio,
    b.rede,
    coalesce(s.taxa_alfabetizacao, b.taxa_alfabetizacao) as taxa_alfabetizacao,
    case when s.event_id is null then 'batch_oficial' else 'stream_simulacao' end as origem
from batch_atual as b
left join stream_atual as s
    on b.id_municipio = s.id_municipio and b.rede = s.rede;

create table duplicate_input (
    event_id string, id_municipio string, taxa double
);
insert into duplicate_input values
('evt-same', '3550308', 70.0), ('evt-same', '3550308', 70.0),
('evt-conflict', '3304557', 60.0), ('evt-conflict', '3304557', 65.0);

create table audit_duplicates as
select
    event_id,
    case
        when count(distinct hash(id_municipio, taxa)) = 1
            then 'identical'
        else 'conflicting'
    end as duplicate_kind
from duplicate_input
group by event_id
having count(*) > 1;

create table quality_results (rule_id string, severity string, action string);
insert into quality_results values
('volume_warning', 'warning', 'continue_with_alert'),
('repeated_rate_critical', 'critical', 'quarantine_and_block');

create table silver_parent (
    release_id string, ano int64, id_municipio string, rede string
);
insert into silver_parent values
('release-a', 2024, '3550308', 'municipal'),
('release-b', 2024, '3550308', 'municipal');

create table silver_students (
    release_id string, ano int64, id_municipio string, rede string,
    student_key string
);
insert into silver_students values
('release-a', 2024, '3550308', 'municipal', 'student-synthetic-1'),
('release-b', 2024, '9999999', 'municipal', 'student-synthetic-2');

create table orphan_students as
select
    a.release_id,
    a.ano,
    a.id_municipio,
    a.rede,
    a.student_key
from silver_students as a
left join silver_parent as p
    on
        a.release_id = p.release_id and a.ano = p.ano
        and a.id_municipio = p.id_municipio and a.rede = p.rede
where p.id_municipio is null;
