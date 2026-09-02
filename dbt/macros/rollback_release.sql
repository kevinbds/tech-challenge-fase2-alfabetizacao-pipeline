{% macro rollback_release(reference_year=none) -%}
    {% set year_text = reference_year | string %}
    {% if not modules.re.fullmatch('[0-9]{4}', year_text) %}
        {{ exceptions.raise_compiler_error('invalid reference_year') }}
    {% endif %}
    {% set normalized_year = year_text | int %}
    {% if normalized_year < 2000 or normalized_year > 2100 %}
        {{ exceptions.raise_compiler_error('invalid reference_year') }}
    {% endif %}
    {{ return(
        adapter.dispatch('rollback_release', 'alfabetizacao_medallion')(normalized_year)
    ) }}
{%- endmacro %}

{% macro rollback_chain(relation, current_release) -%}
    with recursive lineage as (
        select
            release_id,
            reference_year,
            baseline_release_id,
            status,
            0 as chain_level,
            concat('|', release_id, '|') as release_path,
            false as has_cycle
        from {{ relation }}
        where release_id = {{ current_release }}

        union all

        select
            parent.release_id,
            parent.reference_year,
            parent.baseline_release_id,
            parent.status,
            child.chain_level + 1,
            concat(child.release_path, parent.release_id, '|'),
            strpos(child.release_path, concat('|', parent.release_id, '|')) > 0
        from lineage as child
        inner join {{ relation }} as parent
            on parent.release_id = child.baseline_release_id
        where child.baseline_release_id != '__bootstrap__'
            and not child.has_cycle
            and child.chain_level < 400
    )
    select * from lineage
{%- endmacro %}

{% macro bigquery__rollback_release(reference_year) -%}
    {% set sql %}
  declare target_year int64 default {{ reference_year }};
  declare current_release string;
  declare current_prior string;
  declare current_year int64;
  declare current_baseline string;
  declare target_depth int64;
  declare rollback_target string;
  declare rollback_baseline string;
  begin transaction;
  assert target_year between 2000 and 2100 as 'invalid reference_year';
  assert (select count(*) from {{ source('ops', 'active_release') }} where singleton_key)=1
    as 'active release singleton is invalid';
  set (current_release,current_prior)=(select as struct release_id,prior_release_id
    from {{ source('ops', 'active_release') }} where singleton_key);
  assert (select count(*) from {{ source('ops', 'release_registry') }}
    where release_id=current_release and status='active')=1
    as 'active release registry row is invalid';
  assert (select count(*) from {{ source('ops', 'release_registry') }} where status='active')=1
    as 'release registry must contain one active row';
  set (current_year,current_baseline)=(select as struct reference_year,baseline_release_id
    from {{ source('ops', 'release_registry') }}
    where release_id=current_release and status='active');
  assert current_baseline is not null as 'no business release is active';
  assert current_prior is not distinct from
    if(current_baseline='__bootstrap__',null,current_baseline)
    as 'active pointer differs from registry baseline';
  assert target_year <= current_year as 'rollback target cannot be newer than active release';
  create temp table rollback_chain as
    {{ rollback_chain(source('ops', 'release_registry'), 'current_release') }};
  assert (select count(*) from rollback_chain)=
    (select count(distinct release_id) from rollback_chain)
    as 'release ancestry is ambiguous';
  assert not exists(select 1 from rollback_chain where has_cycle)
    as 'release ancestry contains a cycle';
  assert not exists(select 1 from rollback_chain
    where chain_level=400 and baseline_release_id!='__bootstrap__')
    as 'release ancestry exceeds maximum depth';
  assert (select count(*) from rollback_chain where baseline_release_id='__bootstrap__')=1
    as 'release ancestry is dangling';
  assert not exists(select 1 from rollback_chain where
    case when chain_level=0 then status!='active' else status!='inactive' end)
    as 'release ancestry statuses are inconsistent';
  assert not exists(select 1 from rollback_chain as child
    inner join rollback_chain as parent on child.baseline_release_id=parent.release_id
    where child.reference_year < parent.reference_year)
    as 'release ancestry years are inconsistent';
  set target_depth=(select min(chain_level) from rollback_chain
    where reference_year=target_year);
  assert target_depth is not null as 'rollback target year is absent from active history';
  assert (select count(*) from rollback_chain
    where reference_year=target_year and chain_level=target_depth)=1
    as 'rollback target year is ambiguous';
  set (rollback_target,rollback_baseline)=(select as struct release_id,baseline_release_id
    from rollback_chain where reference_year=target_year and chain_level=target_depth);
  update {{ source('ops', 'active_release') }} set release_id=rollback_target,
    prior_release_id=if(rollback_baseline='__bootstrap__',null,rollback_baseline),
    promoted_at=current_timestamp()
  where singleton_key and release_id=current_release
    and prior_release_id is not distinct from current_prior
    and rollback_target!=current_release;
  assert @@row_count=if(rollback_target=current_release,0,1)
    as 'active release changed during rollback';
  update {{ source('ops', 'release_registry') }} set status='inactive'
    where release_id=current_release and status='active' and rollback_target!=current_release;
  assert @@row_count=if(rollback_target=current_release,0,1)
    as 'current registry row changed during rollback';
  update {{ source('ops', 'release_registry') }} set status='active',promoted_at=current_timestamp()
    where release_id=rollback_target and status='inactive' and rollback_target!=current_release;
  assert @@row_count=if(rollback_target=current_release,0,1)
    as 'target registry row changed during rollback';
  assert (select count(*) from {{ source('ops', 'release_registry') }} where status='active')=1
    as 'release registry must contain one active row';
  drop table rollback_chain;
  commit transaction;
  {% endset %}
    {% do run_query(sql) %}
{%- endmacro %}

{% macro duckdb__rollback_release(reference_year) -%}
    {% set guard = "select case when (%s) then 1 else error('%s') end" %}
    {% set sql %}
        begin transaction;
        {{ guard | format(
            "(select count(*) from ops.active_release where singleton_key) = 1",
            "active release singleton is invalid"
        ) }};
        {{ guard | format(
            "(select count(*) from ops.release_registry where status = 'active') = 1",
            "release registry must contain one active row"
        ) }};
        create temp table rollback_chain as
            {{ rollback_chain(
                'ops.release_registry',
                '(select release_id from ops.active_release where singleton_key)'
            ) }};
        {{ guard | format(
            "(select count(*) = count(distinct release_id) from rollback_chain)",
            "release ancestry is ambiguous"
        ) }};
        {{ guard | format(
            "not exists(select 1 from rollback_chain where has_cycle)",
            "release ancestry contains a cycle"
        ) }};
        {{ guard | format(
            "not exists(select 1 from rollback_chain where chain_level = 400 "
            ~ "and baseline_release_id != '__bootstrap__')",
            "release ancestry exceeds maximum depth"
        ) }};
        {{ guard | format(
            "(select count(*) from rollback_chain "
            ~ "where baseline_release_id = '__bootstrap__') = 1",
            "release ancestry is dangling"
        ) }};
        {{ guard | format(
            "not exists(select 1 from rollback_chain where case when chain_level = 0 "
            ~ "then status != 'active' else status != 'inactive' end)",
            "release ancestry statuses are inconsistent"
        ) }};
        {{ guard | format(
            "not exists(select 1 from rollback_chain as child "
            ~ "inner join rollback_chain as parent "
            ~ "on child.baseline_release_id = parent.release_id "
            ~ "where child.reference_year < parent.reference_year)",
            "release ancestry years are inconsistent"
        ) }};
        {{ guard | format(
            "(select prior_release_id is not distinct from "
            ~ "if(baseline_release_id = '__bootstrap__', null, baseline_release_id) "
            ~ "from ops.active_release inner join rollback_chain "
            ~ "on singleton_key and chain_level = 0)",
            "active pointer differs from registry baseline"
        ) }};
        {{ guard | format(
            reference_year ~ " <= (select reference_year from rollback_chain where chain_level = 0)",
            "rollback target cannot be newer than active release"
        ) }};
        create temp table rollback_target as
        select release_id, baseline_release_id
        from rollback_chain
        where reference_year = {{ reference_year }}
        order by chain_level
        limit 1;
        {{ guard | format(
            "(select count(*) from rollback_target) = 1",
            "rollback target year is absent from active history"
        ) }};
        update ops.active_release
        set
            release_id = (select release_id from rollback_target),
            prior_release_id = (
                select nullif(baseline_release_id, '__bootstrap__') from rollback_target
            ),
            promoted_at = current_timestamp
        where singleton_key
            and release_id != (select release_id from rollback_target);
        update ops.release_registry
        set status = 'inactive'
        where status = 'active'
            and release_id != (select release_id from rollback_target);
        update ops.release_registry
        set status = 'active', promoted_at = current_timestamp
        where status = 'inactive'
            and release_id = (select release_id from rollback_target);
        {{ guard | format(
            "(select count(*) from ops.active_release inner join rollback_target "
            ~ "on singleton_key and ops.active_release.release_id = rollback_target.release_id "
            ~ "and prior_release_id is not distinct from "
            ~ "nullif(baseline_release_id, '__bootstrap__')) = 1",
            "active release changed during rollback"
        ) }};
        {{ guard | format(
            "(select count(*) from ops.release_registry where status = 'active') = 1",
            "release registry must contain one active row"
        ) }};
        drop table rollback_target;
        drop table rollback_chain;
        commit;
    {% endset %}
    {% do run_query(sql) %}
{%- endmacro %}
