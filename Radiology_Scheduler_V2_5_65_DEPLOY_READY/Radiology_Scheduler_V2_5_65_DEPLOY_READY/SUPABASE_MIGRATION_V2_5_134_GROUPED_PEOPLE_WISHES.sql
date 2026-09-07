-- V2.5.134 — grupiniai „Dirbti su / Dirbti be“ pageidavimai.
-- Vienas loginis pageidavimas gali turėti kelis žmones, bendrą datą / laiką / vietą.
-- UI leidžia tik dvi realias bendro darbo zonas: CENTRO RO ir ADC 144/145.

alter table public.operator_private_pair_preferences_v25128
  add column if not exists group_id uuid;

update public.operator_private_pair_preferences_v25128
set group_id=gen_random_uuid()
where group_id is null;

alter table public.operator_private_pair_preferences_v25128
  alter column group_id set default gen_random_uuid();

alter table public.operator_private_pair_preferences_v25128
  alter column group_id set not null;

-- Išsaugome senų įrašų suderinamumą, bet nauja UI kuria tik CENTRO RO / ADC 144/145.
alter table public.operator_private_pair_preferences_v25128
  drop constraint if exists operator_private_pair_preferences_v25128_workplace_check;

alter table public.operator_private_pair_preferences_v25128
  add constraint operator_private_pair_preferences_v25128_workplace_check
  check (workplace in (
    'ANY','CENTRO RO','Onko RO','SPS RO','Centro UG','SPS UG',
    'ADC 144','ADC 145','ADC 144/145','Vaikų UG','Mamografijos'
  ));

-- Senas indeksas neleisdavo turėti dviejų atskirų grupių su ta pačia diena / vieta.
-- Nuo V2.5.134 grupės identitetas yra group_id.
drop index if exists public.operator_private_pair_unique_v25128;
create unique index if not exists operator_private_group_target_unique_v25134
on public.operator_private_pair_preferences_v25128(group_id,target_initials);

create index if not exists idx_operator_private_group_v25134
on public.operator_private_pair_preferences_v25128(group_id);

create or replace function public.operator_create_private_group_preference_v25134(
  p_year integer,
  p_month integer,
  p_preference_type text,
  p_target_initials text[],
  p_scope_type text,
  p_scope_start_date date,
  p_block text,
  p_workplace text
)
returns setof public.operator_private_pair_preferences_v25128
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_actor text;
  v_group uuid:=gen_random_uuid();
  v_targets text[];
  v_count integer;
  v_month_start date:=make_date(p_year,p_month,1);
  v_month_end date:=(make_date(p_year,p_month,1)+interval '1 month - 1 day')::date;
begin
  select up.initials into v_actor
  from public.user_profiles up
  where up.user_id=v_uid and up.approved=true
  limit 1;

  if v_actor not in ('SP','ŠR') then raise exception 'PRIVATE_OPERATOR_ONLY'; end if;
  if p_preference_type not in ('together','apart') then raise exception 'INVALID_GROUP_TYPE'; end if;
  if p_scope_type not in ('month','week','day') then raise exception 'INVALID_GROUP_SCOPE'; end if;
  if coalesce(p_block,'ANY') not in ('ANY','AM','PM') then raise exception 'INVALID_GROUP_BLOCK'; end if;
  if p_workplace not in ('CENTRO RO','ADC 144/145') then raise exception 'INVALID_GROUP_WORKPLACE'; end if;

  select coalesce(array_agg(x order by x),array[]::text[])
  into v_targets
  from (
    select distinct trim(t) as x
    from unnest(coalesce(p_target_initials,array[]::text[])) as t
    where trim(t)<>'' and trim(t)<>v_actor
  ) q;

  v_count:=coalesce(array_length(v_targets,1),0);
  if v_count<1 then raise exception 'GROUP_TARGET_REQUIRED'; end if;
  if p_preference_type='together' and p_workplace='CENTRO RO' and v_count>3 then
    raise exception 'CENTRO_GROUP_MAX_4_WITH_OWNER';
  end if;
  if p_preference_type='together' and p_workplace='ADC 144/145' and v_count>1 then
    raise exception 'ADC_GROUP_IS_PAIR';
  end if;
  if exists(
    select 1 from unnest(v_targets) t
    where not exists(
      select 1 from public.resident_directory rd
      where rd.initials=t and coalesce(rd.active,true)=true
    )
  ) then raise exception 'INVALID_GROUP_TARGET'; end if;

  if p_scope_type='month' and p_scope_start_date is not null then raise exception 'MONTH_SCOPE_DATE_MUST_BE_NULL'; end if;
  if p_scope_type in ('week','day') then
    if p_scope_start_date is null then raise exception 'GROUP_SCOPE_DATE_REQUIRED'; end if;
    if p_scope_start_date < v_month_start or p_scope_start_date > v_month_end then raise exception 'GROUP_SCOPE_DATE_OUTSIDE_MONTH'; end if;
  end if;

  insert into public.operator_private_pair_preferences_v25128(
    group_id,owner_initials,year,month,preference_type,target_initials,
    scope_type,scope_start_date,block,workplace
  )
  select
    v_group,v_actor,p_year,p_month,p_preference_type,t,
    p_scope_type,p_scope_start_date,coalesce(p_block,'ANY'),p_workplace
  from unnest(v_targets) t;

  insert into public.operator_private_pair_preference_audit_v25128(
    year,month,actor_user_id,actor_initials,owner_initials,action,preference_id,payload
  ) values(
    p_year,p_month,v_uid,v_actor,v_actor,'create',null,
    jsonb_build_object(
      'group_id',v_group,'targets',to_jsonb(v_targets),'preference_type',p_preference_type,
      'scope_type',p_scope_type,'scope_start_date',p_scope_start_date,
      'block',coalesce(p_block,'ANY'),'workplace',p_workplace
    )
  );

  return query
  select * from public.operator_private_pair_preferences_v25128
  where group_id=v_group
  order by id;
end;
$$;

create or replace function public.operator_delete_private_group_preference_v25134(p_group_id uuid)
returns boolean
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_actor text;
  v_year integer;
  v_month integer;
  v_payload jsonb;
begin
  select up.initials into v_actor
  from public.user_profiles up
  where up.user_id=v_uid and up.approved=true
  limit 1;
  if v_actor not in ('SP','ŠR') then raise exception 'PRIVATE_OPERATOR_ONLY'; end if;

  select min(year),min(month),jsonb_agg(to_jsonb(p) order by p.id)
  into v_year,v_month,v_payload
  from public.operator_private_pair_preferences_v25128 p
  where p.group_id=p_group_id and p.owner_initials=v_actor;

  if v_year is null then return false; end if;

  delete from public.operator_private_pair_preferences_v25128
  where group_id=p_group_id and owner_initials=v_actor;

  insert into public.operator_private_pair_preference_audit_v25128(
    year,month,actor_user_id,actor_initials,owner_initials,action,preference_id,payload
  ) values(
    v_year,v_month,v_uid,v_actor,v_actor,'delete',null,
    jsonb_build_object('group_id',p_group_id,'rows',coalesce(v_payload,'[]'::jsonb))
  );
  return true;
end;
$$;

grant execute on function public.operator_create_private_group_preference_v25134(integer,integer,text,text[],text,date,text,text) to authenticated;
grant execute on function public.operator_delete_private_group_preference_v25134(uuid) to authenticated;
