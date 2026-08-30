create table active_release as
select true as singleton_key, 'release-a'::varchar as release_id,
       timestamp '2024-06-01 00:00:00' as promoted_at;

create table silver_municipio as
select * from (values
  ('release-a', 2023, '3304557', 'estadual', 70.0),
  ('release-a', 2023, '3550308', 'municipal', 60.0),
  ('release-a', 2024, '3304557', 'estadual', 73.0),
  ('release-a', 2024, '3550308', 'municipal', 68.0),
  ('release-old', 2024, '3550308', 'municipal', 10.0)
) as t(release_id, ano, id_municipio, rede, taxa_alfabetizacao);

create table diretorio_municipio as
select * from (values
  ('3304557', 'Rio de Janeiro', 'RJ'),
  ('3550308', 'São Paulo', 'SP')
) as t(id_municipio, nome_municipio, sigla_uf);

create table silver_meta_municipio as
select * from (values
  ('release-a', 2023, '3304557', 'estadual', 72.0, 75.0),
  ('release-a', 2023, '3550308', 'municipal', 65.0, 70.0),
  ('release-a', 2024, '3550308', 'municipal', 67.0, null)
) as t(release_id, ano_referencia, id_municipio, rede,
       meta_alfabetizacao_2024, meta_alfabetizacao_2025);

create table stream_events as
select * from (values
  ('event-old', '3550308', 'municipal', 2024, 66.0, true,
   timestamp '2024-05-30 12:00:00', timestamp '2024-05-30 12:00:01'),
  ('event-a', '3550308', 'municipal', 2024, 71.0, true,
   timestamp '2024-06-02 12:00:00', timestamp '2024-06-02 12:00:01'),
  ('event-z', '3550308', 'municipal', 2024, 72.0, true,
   timestamp '2024-06-02 12:00:00', timestamp '2024-06-02 12:00:02')
) as t(event_id, id_municipio, rede, ano, taxa_alfabetizacao, simulation,
       event_time, publish_time);

create table gold_indicador_municipio as
select m.ano, m.id_municipio, m.rede, m.taxa_alfabetizacao,
       d.nome_municipio, d.sigla_uf, m.release_id
from silver_municipio m
join active_release ar on ar.singleton_key and ar.release_id = m.release_id
join diretorio_municipio d using (id_municipio);

create table gold_comparativo_meta_resultado as
with metas as (
  select release_id, ano_referencia, id_municipio, rede, ano_meta_nome,
         meta_alfabetizacao
  from silver_meta_municipio
  unpivot include nulls (
    meta_alfabetizacao for ano_meta_nome in (
      meta_alfabetizacao_2024, meta_alfabetizacao_2025
    )
  )
), metas_tipadas as (
  select * exclude (ano_meta_nome),
         cast(right(ano_meta_nome, 4) as integer) as ano_meta
  from metas
), escolhidas as (
  select *, row_number() over (
    partition by release_id, ano_meta, id_municipio, rede
    order by ano_referencia desc
  ) as ordem
  from metas_tipadas
  where ano_referencia <= ano_meta and meta_alfabetizacao is not null
)
select i.ano as ano_resultado, 'municipio'::varchar as nivel_geografico,
       i.id_municipio as id_geografia, i.rede, e.ano_referencia,
       e.meta_alfabetizacao, i.taxa_alfabetizacao as taxa_resultado,
       i.taxa_alfabetizacao - e.meta_alfabetizacao as gap_pp,
       case when i.taxa_alfabetizacao >= e.meta_alfabetizacao
            then 'atingida' else 'nao_atingida' end as status_meta,
       i.release_id
from gold_indicador_municipio i
join escolhidas e on e.release_id = i.release_id
  and e.ano_meta = i.ano and e.id_municipio = i.id_municipio
  and e.rede = i.rede and e.ordem = 1;

create table gold_evolucao_alfabetizacao as
with base as (
  select *, lag(taxa_alfabetizacao) over (
    partition by id_municipio, rede order by ano
  ) as taxa_ano_anterior
  from gold_indicador_municipio
)
select *, taxa_alfabetizacao - taxa_ano_anterior as variacao_pp from base;

create table gold_indicador_atual_hibrido as
with batch_atual as (
  select * from gold_indicador_municipio
  qualify row_number() over (
    partition by id_municipio, rede order by ano desc
  ) = 1
), stream_atual as (
  select s.* from stream_events s
  join active_release ar on ar.singleton_key
  where s.simulation and s.event_time > ar.promoted_at
  qualify row_number() over (
    partition by id_municipio, rede order by event_time desc, publish_time desc, event_id desc
  ) = 1
)
select b.id_municipio, b.rede,
       coalesce(s.taxa_alfabetizacao, b.taxa_alfabetizacao) as taxa_alfabetizacao,
       case when s.event_id is null then 'batch_oficial' else 'stream_simulacao' end as origem
from batch_atual b
left join stream_atual s using (id_municipio, rede);

create table duplicate_input as
select * from (values
  ('evt-same', '3550308', 70.0), ('evt-same', '3550308', 70.0),
  ('evt-conflict', '3304557', 60.0), ('evt-conflict', '3304557', 65.0)
) as t(event_id, id_municipio, taxa);

create table audit_duplicates as
select event_id,
       case when count(distinct hash(id_municipio, taxa)) = 1
            then 'identical' else 'conflicting' end as duplicate_kind
from duplicate_input group by event_id having count(*) > 1;

create table quality_results as
select * from (values
  ('volume_warning', 'warning', 'continue_with_alert'),
  ('repeated_rate_critical', 'critical', 'quarantine_and_block')
) as t(rule_id, severity, action);

create table silver_parent as
select * from (values
  ('release-a', 2024, '3550308', 'municipal'),
  ('release-b', 2024, '3550308', 'municipal')
) as t(release_id, ano, id_municipio, rede);

create table silver_students as
select * from (values
  ('release-a', 2024, '3550308', 'municipal', 'student-synthetic-1'),
  ('release-b', 2024, '9999999', 'municipal', 'student-synthetic-2')
) as t(release_id, ano, id_municipio, rede, student_key);

create table orphan_students as
select a.* from silver_students a
left join silver_parent p using (release_id, ano, id_municipio, rede)
where p.id_municipio is null;
