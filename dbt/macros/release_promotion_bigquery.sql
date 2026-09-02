{% macro bigquery__promote_release(release_id) -%}
    {% set sql %}
  declare current_release string;
  declare prior_release string;
  begin transaction;
  assert (select count(*) from {{ source('ops', 'active_release') }} where singleton_key)=1
    as 'active release singleton is invalid';
  set (current_release,prior_release)=(select as struct release_id,prior_release_id
    from {{ source('ops', 'active_release') }} where singleton_key);
  assert current_release is not null as 'active release pointer cannot be null';
  assert prior_release is null or prior_release!=current_release
    as 'active release cannot reference itself as prior';
  assert (select count(*) from {{ source('ops', 'release_registry') }}
    where release_id=current_release)=1
    as 'active release pointer must resolve to exactly one registry row';
  assert (select count(*) from {{ source('ops', 'release_registry') }}
    where release_id=current_release and status='active')=1
    as 'active release pointer must resolve to exactly one active registry row';
  assert prior_release is null or (
    (select count(*) from {{ source('ops', 'release_registry') }}
      where release_id=prior_release)=1
    and (select count(*) from {{ source('ops', 'release_registry') }}
      where release_id=prior_release and status='inactive')=1
  ) as 'prior release pointer must resolve to exactly one inactive registry row';
  assert (select count(*) from {{ source('ops', 'release_registry') }}
    where release_id='{{ release_id }}')=1
    as 'candidate release must resolve to exactly one registry row';
  if current_release='{{ release_id }}' then
    assert (select count(*) from {{ source('ops', 'release_registry') }}
      where release_id='{{ release_id }}' and status='active')=1
      as 'active replay is inconsistent';
  else
    assert (select count(*) from {{ source('ops', 'release_registry') }}
      where release_id='{{ release_id }}' and status='succeeded'
      and baseline_release_id=current_release
      and (current_release='__bootstrap__' or reference_year >= (
        select reference_year from {{ source('ops', 'release_registry') }}
        where release_id=current_release and status='active'
      )))=1
      as 'candidate state or quality baseline differs';
    assert (select count(*) from {{ source('quality', 'release_results') }}
      where release_id='{{ release_id }}')=13 as 'quality result count differs';
    assert (select count(distinct rule_id) from {{ source('quality', 'release_results') }}
      where release_id='{{ release_id }}' and rule_id in ({{ release_rule_list() }}))=13
      as 'quality rule catalog differs';
    assert (select count(*) from {{ source('quality', 'release_results') }}
      where release_id='{{ release_id }}' and
      (severity='critical' or action in ('block_promotion','quarantine_and_block')))=0
      as 'candidate has blocking quality results';
    update {{ source('ops', 'active_release') }} set release_id='{{ release_id }}',
      prior_release_id=if(current_release='__bootstrap__',null,current_release),
      promoted_at=current_timestamp()
    where singleton_key and release_id=current_release
      and prior_release_id is not distinct from prior_release;
    assert @@row_count=1 as 'active release changed during promotion';
    update {{ source('ops', 'release_registry') }} set status='active',promoted_at=current_timestamp()
      where release_id='{{ release_id }}' and status='succeeded';
    assert @@row_count=1 as 'candidate changed during promotion';
    update {{ source('ops', 'release_registry') }} set status='inactive'
      where release_id=current_release and status='active';
    assert @@row_count=1 as 'prior release changed during promotion';
  end if;
  commit transaction;
  {% endset %}
    {% do run_query(sql) %}
{%- endmacro %}
