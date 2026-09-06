-- V2.5.118 — WEEKEND FCFS DUBLIAI + FIRST-SUBMISSION PRIORITY
-- New rules start with the November 2026 schedule. October and older stay reproducible.

create or replace function public.preference_window_open_v25118(p_year integer, p_month integer)
returns timestamptz
language plpgsql
immutable
set search_path to 'public'
as $$
declare
  py integer;
  pm integer;
begin
  if p_month=1 then py:=p_year-1; pm:=12; else py:=p_year; pm:=p_month-1; end if;
  return (make_date(py,pm,1)::timestamp at time zone 'Europe/Vilnius');
end;
$$;

create table if not exists public.preference_priority_points_v25118 (
  year integer not null,
  month integer not null check (month between 1 and 12),
  initials text not null references public.resident_directory(initials) on update cascade,
  first_submitted_at timestamptz not null default now(),
  submission_order integer,
  points_awarded integer not null default 0 check (points_awarded between 0 and 16),
  source text not null default 'resident',
  created_at timestamptz not null default now(),
  primary key (year,month,initials)
);

create unique index if not exists preference_priority_points_v25118_order_uidx
on public.preference_priority_points_v25118(year,month,submission_order)
where submission_order is not null;

alter table public.preference_priority_points_v25118 enable row level security;

drop policy if exists "preference priority authenticated read" on public.preference_priority_points_v25118;
create policy "preference priority authenticated read"
on public.preference_priority_points_v25118
for select to authenticated
using (true);

revoke insert, update, delete on public.preference_priority_points_v25118 from authenticated, anon;
grant select on public.preference_priority_points_v25118 to authenticated;

create or replace function public._register_preference_priority_v25118(
  p_year integer,
  p_month integer,
  p_initials text,
  p_source text
)
returns void
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_order integer;
  v_points integer;
begin
  -- Start on the clean November-2026 cycle. Historical months remain untouched.
  if (p_year*100+p_month) < 202611 then return; end if;

  if exists(
    select 1 from public.preference_priority_points_v25118
    where year=p_year and month=p_month and initials=p_initials
  ) then return; end if;

  -- Serialize first submissions so two simultaneous saves cannot both become #1.
  perform pg_advisory_xact_lock(25118, p_year*100+p_month);

  if exists(
    select 1 from public.preference_priority_points_v25118
    where year=p_year and month=p_month and initials=p_initials
  ) then return; end if;

  if coalesce(p_source,'')='deadline_zero' then
    insert into public.preference_priority_points_v25118(
      year,month,initials,first_submitted_at,submission_order,points_awarded,source
    ) values (p_year,p_month,p_initials,now(),null,0,'deadline_zero');
    return;
  end if;

  select count(*)::integer + 1 into v_order
  from public.preference_priority_points_v25118
  where year=p_year and month=p_month and submission_order is not null;

  v_points:=greatest(0,17-v_order); -- #1=16 ... #16=1

  insert into public.preference_priority_points_v25118(
    year,month,initials,first_submitted_at,submission_order,points_awarded,source
  ) values (p_year,p_month,p_initials,now(),v_order,v_points,coalesce(nullif(p_source,''),'resident'));
end;
$$;

revoke all on function public._register_preference_priority_v25118(integer,integer,text,text) from public;

-- Resident save: enforce the new month-opening boundary and capture the first submission rank.
create or replace function public.save_my_preferences_v2595(p_year integer, p_month integer, p_payload jsonb)
returns public.preferences
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_initials text;
  v_open timestamptz;
  v_cutoff timestamptz;
  v_row public.preferences%rowtype;
begin
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select up.initials into v_initials from public.user_profiles up
    where up.user_id=v_uid and up.approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory rd where rd.initials=v_initials and coalesce(rd.active,true)=true)
    then raise exception 'ACTIVE_RESIDENT_REQUIRED'; end if;

  v_open:=public.preference_window_open_v25118(p_year,p_month);
  v_cutoff:=public.preference_cutoff_v2595(p_year,p_month);
  if (p_year*100+p_month)>=202611 and now()<v_open then raise exception 'PREFERENCE_WINDOW_NOT_OPEN'; end if;
  if now()>=v_cutoff then raise exception 'PREFERENCE_DEADLINE_CLOSED'; end if;
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'PREFERENCE_INPUT_FROZEN_AFTER_SYSTEM'; end if;

  v_row:=public._preference_payload_row_v2595(p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb),'resident',v_uid,v_initials);
  perform public._register_preference_priority_v25118(p_year,p_month,v_initials,'resident');
  return v_row;
end;
$$;

-- Operator entry remains possible outside the ordinary window, but its FIRST entry still receives
-- the timestamp/order that actually occurred. This preserves the senior's always-on manual authority.
create or replace function public.save_preferences_for_resident_v2595(
  p_year integer, p_month integer, p_target_initials text, p_payload jsonb, p_reason text
)
returns public.preferences
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_actor text;
  v_before jsonb;
  v_row public.preferences%rowtype;
begin
  if not public.is_lifecycle_operator_v2592(v_uid) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  select up.initials into v_actor from public.user_profiles up where up.user_id=v_uid and up.approved=true limit 1;
  if v_actor is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory rd where rd.initials=p_target_initials and coalesce(rd.active,true)=true)
    then raise exception 'UNKNOWN_OR_INACTIVE_RESIDENT'; end if;
  if coalesce(trim(p_reason),'')='' then raise exception 'OPERATOR_ENTRY_REASON_REQUIRED'; end if;
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'PREFERENCE_INPUT_FROZEN_AFTER_SYSTEM'; end if;

  select to_jsonb(p) into v_before from public.preferences p where p.year=p_year and p.month=p_month and p.initials=p_target_initials;
  v_row:=public._preference_payload_row_v2595(p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb),'operator_manual',v_uid,v_actor);
  perform public._register_preference_priority_v25118(p_year,p_month,p_target_initials,'operator_manual');

  insert into public.preference_operator_audit(year,month,target_initials,actor_user_id,actor_initials,reason,before_json,after_json)
  values(p_year,p_month,p_target_initials,v_uid,v_actor,trim(p_reason),v_before,to_jsonb(v_row));
  return v_row;
end;
$$;



-- Deadline auto-zero rows participate in the ledger transparently but earn 0 points.
create or replace function public.auto_submit_zero_preferences_v2594(p_year integer, p_month integer, p_cutoff timestamptz)
returns jsonb
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_inserted text[]:=array[]::text[];
  v_initials text;
  v_server_cutoff timestamptz;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  v_server_cutoff:=public.preference_cutoff_v2595(p_year,p_month);
  if now()<v_server_cutoff then
    return jsonb_build_object('ok',true,'due',false,'count',0,'initials','[]'::jsonb,'cutoff',v_server_cutoff);
  end if;
  for v_initials in
    select rd.initials from public.resident_directory rd
    where coalesce(rd.active,true)=true
      and not exists(select 1 from public.preferences p where p.year=p_year and p.month=p_month and p.initials=rd.initials)
    order by rd.initials
  loop
    insert into public.preferences(
      year,month,initials,
      unavailable,unavailable_am,unavailable_pm,justified_absence,vacation,long_duty,
      soft_free,soft_free_am,soft_free_pm,preferred,preferred_am,preferred_pm,
      note,prior_weekend_count,backup_credits_to_use,backup_credits_am_to_use,backup_credits_pm_to_use,backup_credits_night_to_use,
      submission_source,submitted_at,submitted_by_user_id,submitted_by_initials,updated_at
    ) values(
      p_year,p_month,v_initials,
      '[]','[]','[]','[]','[]','[]','[]','[]','[]','[]','[]','[]',
      '',0,0,0,0,0,
      'deadline_zero',v_server_cutoff,null,'SYSTEM',now()
    ) on conflict(year,month,initials) do nothing;
    if found then
      v_inserted:=array_append(v_inserted,v_initials);
      perform public._register_preference_priority_v25118(p_year,p_month,v_initials,'deadline_zero');
    end if;
  end loop;
  return jsonb_build_object('ok',true,'due',true,'count',coalesce(array_length(v_inserted,1),0),'initials',to_jsonb(coalesce(v_inserted,array[]::text[])),'source','deadline_zero','cutoff',v_server_cutoff);
end;
$$;

-- From the November-2026 cycle residents must use the atomic FCFS RPC rather
-- than direct table writes. Historical months keep their legacy self-service;
-- SP/senior direct administration remains allowed by the senior ALL policy.
drop policy if exists "weekend claim own insert" on public.weekend_backup_claims;
create policy "weekend claim own insert"
on public.weekend_backup_claims
for insert to authenticated
with check (
  (year*100+month)<202611
  and initials=(select up.initials from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true)
);

drop policy if exists "weekend claim own update before publication" on public.weekend_backup_claims;
create policy "weekend claim own update before publication"
on public.weekend_backup_claims
for update to authenticated
using (
  (year*100+month)<202611
  and initials=(select up.initials from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true)
)
with check (
  (year*100+month)<202611
  and initials=(select up.initials from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true)
);

drop policy if exists "weekend claim own delete" on public.weekend_backup_claims;
create policy "weekend claim own delete"
on public.weekend_backup_claims
for delete to authenticated
using (
  (year*100+month)<202611
  and initials=(select up.initials from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true)
);


-- Atomic first-come-first-served weekend dublis claim.
create or replace function public.claim_weekend_backup_fcfs_v25118(
  p_year integer,
  p_month integer,
  p_covered_slot integer,
  p_day integer,
  p_block text
)
returns public.weekend_backup_claims
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_initials text;
  v_open timestamptz;
  v_cutoff timestamptz;
  v_existing public.weekend_backup_claims%rowtype;
  v_owner public.weekend_backup_claims%rowtype;
  v_count integer;
  v_row public.weekend_backup_claims%rowtype;
begin
  if (p_year*100+p_month)<202611 then raise exception 'FCFS_BACKUP_MODE_NOT_ACTIVE'; end if;
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select initials into v_initials from public.user_profiles
  where user_id=v_uid and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;

  v_open:=public.preference_window_open_v25118(p_year,p_month);
  v_cutoff:=public.preference_cutoff_v2595(p_year,p_month);
  if now()<v_open then raise exception 'BACKUP_WINDOW_NOT_OPEN'; end if;
  if now()>=v_cutoff then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  if p_block not in ('AM','PM') then raise exception 'BACKUP_SLOT_NOT_6H'; end if;
  if p_day<1 or p_day>extract(day from (date_trunc('month',make_date(p_year,p_month,1))+interval '1 month - 1 day'))::integer
    then raise exception 'INVALID_BACKUP_DAY'; end if;
  if extract(isodow from make_date(p_year,p_month,p_day)) not in (6,7)
    then raise exception 'BACKUP_SLOT_NOT_WEEKEND'; end if;

  perform pg_advisory_xact_lock(25119, p_year*100+p_month);

  select * into v_existing from public.weekend_backup_claims
  where year=p_year and month=p_month and initials=v_initials for update;
  if found and v_existing.covered_slot=p_covered_slot then return v_existing; end if;

  select * into v_owner from public.weekend_backup_claims
  where year=p_year and month=p_month and covered_slot=p_covered_slot for update;
  if found and v_owner.initials is distinct from v_initials then
    raise exception 'BACKUP_SLOT_ALREADY_CLAIMED';
  end if;

  select count(*)::integer into v_count
  from public.weekend_backup_claims
  where year=p_year and month=p_month and initials<>v_initials;
  if v_count>=16 then raise exception 'BACKUP_FCFS_FULL'; end if;

  delete from public.weekend_backup_claims
  where year=p_year and month=p_month and initials=v_initials;

  insert into public.weekend_backup_claims(year,month,covered_slot,initials,source,claimed_at,updated_at)
  values(p_year,p_month,p_covered_slot,v_initials,'self_fcfs',now(),now())
  returning * into v_row;
  return v_row;
end;
$$;

grant execute on function public.claim_weekend_backup_fcfs_v25118(integer,integer,integer,integer,text) to authenticated;

create or replace function public.release_weekend_backup_fcfs_v25118(p_year integer,p_month integer)
returns boolean
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_initials text;
  v_open timestamptz;
  v_cutoff timestamptz;
  v_n integer;
begin
  if (p_year*100+p_month)<202611 then raise exception 'FCFS_BACKUP_MODE_NOT_ACTIVE'; end if;
  select initials into v_initials from public.user_profiles
  where user_id=v_uid and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  v_open:=public.preference_window_open_v25118(p_year,p_month);
  v_cutoff:=public.preference_cutoff_v2595(p_year,p_month);
  if now()<v_open then raise exception 'BACKUP_WINDOW_NOT_OPEN'; end if;
  if now()>=v_cutoff then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  delete from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials;
  get diagnostics v_n=row_count;
  return v_n>0;
end;
$$;

grant execute on function public.release_weekend_backup_fcfs_v25118(integer,integer) to authenticated;

-- Backfill any future-cycle rows if they already exist (normally none at deployment time).
with ranked as (
  select year,month,initials,submitted_at,submission_source,
         row_number() over(partition by year,month order by submitted_at,initials) as rn
  from public.preferences
  where (year*100+month)>=202611 and submission_source<>'deadline_zero'
)
insert into public.preference_priority_points_v25118(year,month,initials,first_submitted_at,submission_order,points_awarded,source)
select year,month,initials,submitted_at,rn::integer,greatest(0,17-rn::integer),submission_source
from ranked
on conflict (year,month,initials) do nothing;
