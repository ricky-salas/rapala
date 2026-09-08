-- V2.5.145 — SVEIKATINIMOSI / KVALIFIKACIJOS KĖLIMO DIENOS
-- Separate from preferences on purpose:
--  * they are PAID working days outside the clinical rota;
--  * they do NOT enter wish statistics;
--  * they do NOT change preference submission priority;
--  * they block a clinical assignment on that calendar day.

create table if not exists public.resident_special_workdays_v25145 (
  year integer not null,
  month integer not null check (month between 1 and 12),
  initials text not null,
  wellness_days integer[] not null default '{}'::integer[],
  qualification_days integer[] not null default '{}'::integer[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (year,month,initials)
);

alter table public.resident_special_workdays_v25145 enable row level security;

-- Group schedule data is already visible to approved residents. Keep reads simple;
-- writes remain RPC-only and identity checked below.
drop policy if exists special_workdays_read_v25145 on public.resident_special_workdays_v25145;
create policy special_workdays_read_v25145
on public.resident_special_workdays_v25145
for select to authenticated
using (
  exists (
    select 1 from public.user_profiles up
    where up.user_id=auth.uid() and up.approved=true
  )
);

grant select on public.resident_special_workdays_v25145 to authenticated;
revoke insert,update,delete on public.resident_special_workdays_v25145 from authenticated;

create or replace function public._upsert_special_workdays_v25145(
  p_year integer,p_month integer,p_initials text,p_payload jsonb
)
returns public.resident_special_workdays_v25145
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_well integer[] := '{}'::integer[];
  v_qual integer[] := '{}'::integer[];
  v_last integer;
  v_bad integer;
  v_row public.resident_special_workdays_v25145%rowtype;
begin
  v_last:=extract(day from (make_date(p_year,p_month,1)+interval '1 month - 1 day'))::integer;

  select coalesce(array_agg(distinct x order by x),'{}'::integer[])
  into v_well
  from (
    select value::integer as x
    from jsonb_array_elements_text(coalesce(p_payload->'wellness_days','[]'::jsonb))
  ) q;

  select coalesce(array_agg(distinct x order by x),'{}'::integer[])
  into v_qual
  from (
    select value::integer as x
    from jsonb_array_elements_text(coalesce(p_payload->'qualification_days','[]'::jsonb))
  ) q;

  select x into v_bad from unnest(v_well || v_qual) x where x<1 or x>v_last limit 1;
  if v_bad is not null then raise exception 'SPECIAL_WORKDAY_INVALID_DATE'; end if;
  if exists(select 1 from unnest(v_well) as w(day) join unnest(v_qual) as q(day) using(day)) then
    raise exception 'SPECIAL_WORKDAY_TYPE_CONFLICT';
  end if;

  insert into public.resident_special_workdays_v25145(
    year,month,initials,wellness_days,qualification_days,updated_at
  ) values (
    p_year,p_month,p_initials,v_well,v_qual,now()
  )
  on conflict (year,month,initials) do update
  set wellness_days=excluded.wellness_days,
      qualification_days=excluded.qualification_days,
      updated_at=now()
  returning * into v_row;
  return v_row;
end;
$$;
revoke all on function public._upsert_special_workdays_v25145(integer,integer,text,jsonb) from public;

-- Re-wrap current resident save so preferences + special workdays commit atomically.
-- Special fields are intentionally NOT part of the V2.5.136 priority fingerprint.
create or replace function public.save_my_preferences_v2595(p_year integer,p_month integer,p_payload jsonb)
returns public.preferences
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid(); v_initials text; v_open timestamptz; v_cutoff timestamptz; v_row public.preferences%rowtype;
begin
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select up.initials into v_initials from public.user_profiles up where up.user_id=v_uid and up.approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory rd where rd.initials=v_initials and coalesce(rd.active,true)=true)
    then raise exception 'ACTIVE_RESIDENT_REQUIRED'; end if;
  v_open:=public.preference_window_open_v25118(p_year,p_month);
  v_cutoff:=public.preference_cutoff_v2595(p_year,p_month);
  if (p_year*100+p_month)>=202610 and now()<v_open then raise exception 'PREFERENCE_WINDOW_NOT_OPEN'; end if;
  if now()>=v_cutoff then raise exception 'PREFERENCE_DEADLINE_CLOSED'; end if;
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'PREFERENCE_INPUT_FROZEN_AFTER_SYSTEM'; end if;

  v_row:=public._preference_payload_row_v2595(
    p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb),'resident',v_uid,v_initials
  );
  perform public._upsert_special_workdays_v25145(p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb));
  perform public._apply_preference_integrity_guard_v25136(
    p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb),'resident'
  );
  return v_row;
end;
$$;
grant execute on function public.save_my_preferences_v2595(integer,integer,jsonb) to authenticated;

create or replace function public.save_preferences_for_resident_v2595(
  p_year integer,p_month integer,p_target_initials text,p_payload jsonb,p_reason text
)
returns public.preferences
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_uid uuid:=auth.uid(); v_actor text; v_before jsonb; v_row public.preferences%rowtype;
begin
  if not public.is_lifecycle_operator_v2592(v_uid) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  select up.initials into v_actor from public.user_profiles up where up.user_id=v_uid and up.approved=true limit 1;
  if v_actor is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory rd where rd.initials=p_target_initials and coalesce(rd.active,true)=true)
    then raise exception 'UNKNOWN_OR_INACTIVE_RESIDENT'; end if;
  if coalesce(trim(p_reason),'')='' then raise exception 'OPERATOR_ENTRY_REASON_REQUIRED'; end if;

  select to_jsonb(p) into v_before from public.preferences p
  where p.year=p_year and p.month=p_month and p.initials=p_target_initials;

  v_row:=public._preference_payload_row_v2595(
    p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb),'operator_manual',v_uid,v_actor
  );
  perform public._upsert_special_workdays_v25145(
    p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb)
  );
  perform public._apply_preference_integrity_guard_v25136(
    p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb),'operator_manual'
  );

  insert into public.preference_operator_audit(
    year,month,target_initials,actor_user_id,actor_initials,reason,before_json,after_json
  ) values (
    p_year,p_month,p_target_initials,v_uid,v_actor,trim(p_reason),v_before,to_jsonb(v_row)
  );
  return v_row;
end;
$$;
grant execute on function public.save_preferences_for_resident_v2595(integer,integer,text,jsonb,text) to authenticated;

-- Direct Specialios dienos editors. These are intentionally independent from
-- preference submission timing; they may be changed until SYSTEM is published.
create or replace function public.save_my_special_workdays_v25145(
  p_year integer,p_month integer,p_payload jsonb
)
returns public.resident_special_workdays_v25145
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_initials text;
begin
  select up.initials into v_initials from public.user_profiles up
  where up.user_id=auth.uid() and up.approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'SPECIAL_WORKDAYS_FROZEN_AFTER_SYSTEM'; end if;
  return public._upsert_special_workdays_v25145(p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb));
end;
$$;
grant execute on function public.save_my_special_workdays_v25145(integer,integer,jsonb) to authenticated;

create or replace function public.save_special_workdays_for_resident_v25145(
  p_year integer,p_month integer,p_target_initials text,p_payload jsonb
)
returns public.resident_special_workdays_v25145
language plpgsql security definer
set search_path to 'public','auth'
as $$
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory rd where rd.initials=p_target_initials and coalesce(rd.active,true)=true)
    then raise exception 'UNKNOWN_OR_INACTIVE_RESIDENT'; end if;
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'SPECIAL_WORKDAYS_FROZEN_AFTER_SYSTEM'; end if;
  return public._upsert_special_workdays_v25145(p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb));
end;
$$;
grant execute on function public.save_special_workdays_for_resident_v25145(integer,integer,text,jsonb) to authenticated;
