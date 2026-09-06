-- V2.5.119 — AUTOMATIC MONTH PHASES + OCTOBER FCFS DUBLIAI
-- Resident lifecycle (Europe/Vilnius):
--   previous month day 1 00:00 -> day 14 00:00 : monthly preferences open
--   day 14 00:00 -> day 16 00:00              : resident swap window; dublis self-selection remains open
--   from day 16 00:00                           : resident editing closes; missing mandatory dubliai are auto-randomized
-- Senior/operator manual controls are not governed by these resident windows.

create or replace function public.preference_window_open_v25118(p_year integer,p_month integer)
returns timestamptz
language plpgsql immutable
set search_path to 'public'
as $$
declare py integer; pm integer;
begin
  if p_month=1 then py:=p_year-1; pm:=12; else py:=p_year; pm:=p_month-1; end if;
  return (make_date(py,pm,1)::timestamp at time zone 'Europe/Vilnius');
end;
$$;

create or replace function public.swap_window_close_v25119(p_year integer,p_month integer)
returns timestamptz
language plpgsql immutable
set search_path to 'public'
as $$
declare py integer; pm integer;
begin
  if p_month=1 then py:=p_year-1; pm:=12; else py:=p_year; pm:=p_month-1; end if;
  return (make_date(py,pm,16)::timestamp at time zone 'Europe/Vilnius');
end;
$$;

grant execute on function public.swap_window_close_v25119(integer,integer) to authenticated;

create or replace function public.scheduler_cycle_phase_v25119(p_year integer,p_month integer)
returns jsonb
language plpgsql stable
set search_path to 'public'
as $$
declare
  v_open timestamptz:=public.preference_window_open_v25118(p_year,p_month);
  v_pref_close timestamptz:=public.preference_cutoff_v2595(p_year,p_month);
  v_swap_close timestamptz:=public.swap_window_close_v25119(p_year,p_month);
  v_phase text;
begin
  v_phase:=case
    when now()<v_open then 'not_open'
    when now()<v_pref_close then 'preferences'
    when now()<v_swap_close then 'swaps'
    else 'senior_review'
  end;
  return jsonb_build_object(
    'phase',v_phase,'preference_open',v_open,'preference_close',v_pref_close,
    'swap_open',v_pref_close,'swap_close',v_swap_close,'server_now',now()
  );
end;
$$;

grant execute on function public.scheduler_cycle_phase_v25119(integer,integer) to authenticated;

-- Exact 16-slot catalog. Keeping the concrete slot id in DB lets automatic
-- assignment create claims that map directly onto the existing backup layer.
create table if not exists public.weekend_backup_slot_catalog_v25119(
  year integer not null,
  month integer not null check(month between 1 and 12),
  covered_slot integer not null,
  claim_day integer not null,
  claim_block text not null check(claim_block in ('AM','PM')),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  primary key(year,month,covered_slot),
  unique(year,month,claim_day,claim_block)
);
alter table public.weekend_backup_slot_catalog_v25119 enable row level security;
drop policy if exists "weekend backup catalog authenticated read" on public.weekend_backup_slot_catalog_v25119;
create policy "weekend backup catalog authenticated read"
on public.weekend_backup_slot_catalog_v25119 for select to authenticated using(true);
revoke insert,update,delete on public.weekend_backup_slot_catalog_v25119 from authenticated,anon;
grant select on public.weekend_backup_slot_catalog_v25119 to authenticated;

-- October 2026: four complete weekends = exactly sixteen 6h positions.
insert into public.weekend_backup_slot_catalog_v25119(year,month,covered_slot,claim_day,claim_block) values
(2026,10,40,3,'AM'),(2026,10,41,3,'PM'),(2026,10,42,4,'AM'),(2026,10,43,4,'PM'),
(2026,10,144,10,'AM'),(2026,10,145,10,'PM'),(2026,10,146,11,'AM'),(2026,10,147,11,'PM'),
(2026,10,248,17,'AM'),(2026,10,249,17,'PM'),(2026,10,250,18,'AM'),(2026,10,251,18,'PM'),
(2026,10,352,24,'AM'),(2026,10,353,24,'PM'),(2026,10,354,25,'AM'),(2026,10,355,25,'PM'),
(2026,11,102,7,'AM'),(2026,11,103,7,'PM'),(2026,11,104,8,'AM'),(2026,11,105,8,'PM'),
(2026,11,206,14,'AM'),(2026,11,207,14,'PM'),(2026,11,208,15,'AM'),(2026,11,209,15,'PM'),
(2026,11,310,21,'AM'),(2026,11,311,21,'PM'),(2026,11,312,22,'AM'),(2026,11,313,22,'PM'),
(2026,11,414,28,'AM'),(2026,11,415,28,'PM'),(2026,11,416,29,'AM'),(2026,11,417,29,'PM')
on conflict(year,month,covered_slot) do update set claim_day=excluded.claim_day,claim_block=excluded.claim_block,active=true;

create or replace function public.is_fcfs_weekend_backup_slot_v25118(
  p_year integer,p_month integer,p_day integer,p_block text
)
returns boolean
language sql stable
set search_path to 'public'
as $$
  select exists(
    select 1 from public.weekend_backup_slot_catalog_v25119 c
    where c.year=p_year and c.month=p_month and c.claim_day=p_day
      and c.claim_block=p_block and c.active=true
  );
$$;

grant execute on function public.is_fcfs_weekend_backup_slot_v25118(integer,integer,integer,text) to authenticated;

-- First-submission points now start with the October schedule.
create or replace function public._register_preference_priority_v25118(
  p_year integer,p_month integer,p_initials text,p_source text
)
returns void
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_order integer; v_points integer;
begin
  if (p_year*100+p_month)<202610 then return; end if;
  if exists(select 1 from public.preference_priority_points_v25118 where year=p_year and month=p_month and initials=p_initials) then return; end if;
  perform pg_advisory_xact_lock(25118,p_year*100+p_month);
  if exists(select 1 from public.preference_priority_points_v25118 where year=p_year and month=p_month and initials=p_initials) then return; end if;
  if coalesce(p_source,'')='deadline_zero' then
    insert into public.preference_priority_points_v25118(year,month,initials,first_submitted_at,submission_order,points_awarded,source)
    values(p_year,p_month,p_initials,now(),null,0,'deadline_zero');
    return;
  end if;
  select count(*)::integer+1 into v_order from public.preference_priority_points_v25118
  where year=p_year and month=p_month and submission_order is not null;
  v_points:=greatest(0,17-v_order);
  insert into public.preference_priority_points_v25118(year,month,initials,first_submitted_at,submission_order,points_awarded,source)
  values(p_year,p_month,p_initials,now(),v_order,v_points,coalesce(nullif(p_source,''),'resident'));
end;
$$;
revoke all on function public._register_preference_priority_v25118(integer,integer,text,text) from public;

-- Resident monthly preference writes: time-derived, no lifecycle button required.
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
  v_row:=public._preference_payload_row_v2595(p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb),'resident',v_uid,v_initials);
  perform public._register_preference_priority_v25118(p_year,p_month,v_initials,'resident');
  return v_row;
end;
$$;

-- Operator entry stays an operator privilege rather than following resident clock gates.
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
  select to_jsonb(p) into v_before from public.preferences p where p.year=p_year and p.month=p_month and p.initials=p_target_initials;
  v_row:=public._preference_payload_row_v2595(p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb),'operator_manual',v_uid,v_actor);
  perform public._register_preference_priority_v25118(p_year,p_month,p_target_initials,'operator_manual');
  insert into public.preference_operator_audit(year,month,target_initials,actor_user_id,actor_initials,reason,before_json,after_json)
  values(p_year,p_month,p_target_initials,v_uid,v_actor,trim(p_reason),v_before,to_jsonb(v_row));
  return v_row;
end;
$$;

-- FCFS dublis self-selection stays available through the swap window (until day 16 00:00).
create or replace function public.claim_weekend_backup_fcfs_v25118(
  p_year integer,p_month integer,p_covered_slot integer,p_day integer,p_block text
)
returns public.weekend_backup_claims
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid(); v_initials text; v_open timestamptz; v_close timestamptz;
  v_existing public.weekend_backup_claims%rowtype; v_owner public.weekend_backup_claims%rowtype;
  v_count integer; v_row public.weekend_backup_claims%rowtype;
begin
  if (p_year*100+p_month)<202610 then raise exception 'FCFS_BACKUP_MODE_NOT_ACTIVE'; end if;
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select initials into v_initials from public.user_profiles where user_id=v_uid and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  v_open:=public.preference_window_open_v25118(p_year,p_month);
  v_close:=public.swap_window_close_v25119(p_year,p_month);
  if now()<v_open then raise exception 'BACKUP_WINDOW_NOT_OPEN'; end if;
  if now()>=v_close then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  if not exists(select 1 from public.weekend_backup_slot_catalog_v25119 c
                where c.year=p_year and c.month=p_month and c.covered_slot=p_covered_slot
                  and c.claim_day=p_day and c.claim_block=p_block and c.active=true)
    then raise exception 'BACKUP_SLOT_OUTSIDE_16_SLOT_CATALOG'; end if;
  perform pg_advisory_xact_lock(25119,p_year*100+p_month);
  select * into v_existing from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials for update;
  if found and v_existing.covered_slot=p_covered_slot and v_existing.claim_day=p_day and v_existing.claim_block=p_block then return v_existing; end if;
  select * into v_owner from public.weekend_backup_claims where year=p_year and month=p_month
    and (covered_slot=p_covered_slot or (claim_day=p_day and claim_block=p_block)) for update limit 1;
  if found and v_owner.initials is distinct from v_initials then raise exception 'BACKUP_SLOT_ALREADY_CLAIMED'; end if;
  select count(*)::integer into v_count from public.weekend_backup_claims where year=p_year and month=p_month and initials<>v_initials;
  if v_count>=16 then raise exception 'BACKUP_FCFS_FULL'; end if;
  delete from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials;
  insert into public.weekend_backup_claims(year,month,covered_slot,initials,source,claimed_at,updated_at,claim_day,claim_block)
  values(p_year,p_month,p_covered_slot,v_initials,'self_fcfs',now(),now(),p_day,p_block) returning * into v_row;
  return v_row;
end;
$$;
grant execute on function public.claim_weekend_backup_fcfs_v25118(integer,integer,integer,integer,text) to authenticated;

create or replace function public.release_weekend_backup_fcfs_v25118(p_year integer,p_month integer)
returns boolean
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_uid uuid:=auth.uid(); v_initials text; v_open timestamptz; v_close timestamptz; v_n integer;
begin
  if (p_year*100+p_month)<202610 then raise exception 'FCFS_BACKUP_MODE_NOT_ACTIVE'; end if;
  select initials into v_initials from public.user_profiles where user_id=v_uid and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  v_open:=public.preference_window_open_v25118(p_year,p_month); v_close:=public.swap_window_close_v25119(p_year,p_month);
  if now()<v_open then raise exception 'BACKUP_WINDOW_NOT_OPEN'; end if;
  if now()>=v_close then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  delete from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials;
  get diagnostics v_n=row_count; return v_n>0;
end;
$$;
grant execute on function public.release_weekend_backup_fcfs_v25118(integer,integer) to authenticated;

-- At day 16 00:00 every resident who did not self-select receives one of the
-- remaining mandatory positions at random. Existing FCFS/manual claims are preserved.
create or replace function public.auto_fill_weekend_backups_v25119(p_year integer,p_month integer)
returns jsonb
language plpgsql security definer
set search_path to 'public'
as $$
declare
  v_close timestamptz:=public.swap_window_close_v25119(p_year,p_month);
  v_missing_people integer; v_missing_slots integer; v_inserted integer:=0;
begin
  if (p_year*100+p_month)<202610 then return jsonb_build_object('ok',true,'due',false,'reason','legacy_month'); end if;
  if now()<v_close then return jsonb_build_object('ok',true,'due',false,'close',v_close); end if;
  perform pg_advisory_xact_lock(25120,p_year*100+p_month);

  select count(*) into v_missing_people from public.resident_directory rd
  where coalesce(rd.active,true)=true
    and not exists(select 1 from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.initials=rd.initials);
  select count(*) into v_missing_slots from public.weekend_backup_slot_catalog_v25119 c
  where c.year=p_year and c.month=p_month and c.active=true
    and not exists(select 1 from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.covered_slot=c.covered_slot);

  if v_missing_people<>v_missing_slots then
    raise exception 'BACKUP_RANDOM_FILL_COUNT_MISMATCH people=% slots=%',v_missing_people,v_missing_slots;
  end if;

  with people as (
    select rd.initials,row_number() over(order by random()) rn
    from public.resident_directory rd
    where coalesce(rd.active,true)=true
      and not exists(select 1 from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.initials=rd.initials)
  ), slots as (
    select c.covered_slot,c.claim_day,c.claim_block,row_number() over(order by random()) rn
    from public.weekend_backup_slot_catalog_v25119 c
    where c.year=p_year and c.month=p_month and c.active=true
      and not exists(select 1 from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.covered_slot=c.covered_slot)
  )
  insert into public.weekend_backup_claims(year,month,covered_slot,initials,source,claimed_at,updated_at,claim_day,claim_block)
  select p_year,p_month,s.covered_slot,p.initials,'auto_random',now(),now(),s.claim_day,s.claim_block
  from people p join slots s using(rn);
  get diagnostics v_inserted=row_count;
  return jsonb_build_object('ok',true,'due',true,'inserted',v_inserted,'total',(select count(*) from public.weekend_backup_claims where year=p_year and month=p_month));
end;
$$;
grant execute on function public.auto_fill_weekend_backups_v25119(integer,integer) to authenticated;

-- Resident swap authority is derived from the clock. No senior "open/close" button
-- is needed for October-2026 onward. A generated/published SYSTEM must still exist.
create or replace function public._swap_submission_allowed_v2591(p_year integer,p_month integer,p_initials text)
returns boolean
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_state text; v_deadline timestamptz; v_start timestamptz; v_close timestamptz;
begin
  if (p_year*100+p_month)>=202610 then
    v_start:=public.preference_cutoff_v2595(p_year,p_month);
    v_close:=public.swap_window_close_v25119(p_year,p_month);
    if now()<v_start or now()>=v_close then return false; end if;
    if exists(select 1 from public.schedule_lifecycle where year=p_year and month=p_month and state='final') then return false; end if;
    return exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published' and s.baseline_json is not null and s.current_json is not null);
  end if;
  select state,swap_deadline into v_state,v_deadline from public.schedule_lifecycle where year=p_year and month=p_month for update;
  if v_state is null or v_state='final' then return false; end if;
  if v_state='swap_open' and v_deadline is not null and now()<=v_deadline then return true; end if;
  return public._consume_late_swap_access_v2591(p_year,p_month,p_initials);
end;
$$;

-- Keep the stored lifecycle synchronized for UI/audit; clock remains authoritative.
create or replace function public.sync_schedule_cycle_v25119(p_year integer,p_month integer)
returns jsonb
language plpgsql security definer
set search_path to 'public'
as $$
declare
  v_pref_close timestamptz:=public.preference_cutoff_v2595(p_year,p_month);
  v_swap_close timestamptz:=public.swap_window_close_v25119(p_year,p_month);
  v_phase jsonb; v_has_published boolean;
begin
  v_phase:=public.scheduler_cycle_phase_v25119(p_year,p_month);
  if (p_year*100+p_month)<202610 then return v_phase; end if;
  select exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published' and s.current_json is not null) into v_has_published;
  if now()>=v_pref_close and now()<v_swap_close and v_has_published then
    insert into public.schedule_lifecycle(year,month,state,swap_opened_at,swap_deadline,updated_at)
    values(p_year,p_month,'swap_open',v_pref_close,v_swap_close,now())
    on conflict(year,month) do update set
      state=case when public.schedule_lifecycle.state='final' then 'final' else 'swap_open' end,
      swap_opened_at=coalesce(public.schedule_lifecycle.swap_opened_at,v_pref_close),
      swap_deadline=v_swap_close,swap_closed_at=null,updated_at=now();
  elsif now()>=v_swap_close then
    perform public.auto_fill_weekend_backups_v25119(p_year,p_month);
    insert into public.schedule_lifecycle(year,month,state,swap_deadline,swap_closed_at,updated_at)
    values(p_year,p_month,'swap_closed',v_swap_close,v_swap_close,now())
    on conflict(year,month) do update set
      state=case when public.schedule_lifecycle.state='final' then 'final' else 'swap_closed' end,
      swap_deadline=v_swap_close,swap_closed_at=coalesce(public.schedule_lifecycle.swap_closed_at,v_swap_close),updated_at=now();
  end if;
  return public.scheduler_cycle_phase_v25119(p_year,p_month);
end;
$$;
grant execute on function public.sync_schedule_cycle_v25119(integer,integer) to authenticated;

-- Background clock: no human activates stages. Runs every 5 minutes; RPC guards use
-- exact timestamps, so a few-minute cron cadence never extends resident permissions.
create or replace function public.auto_advance_scheduler_cycle_v25119()
returns jsonb
language plpgsql security definer
set search_path to 'public','extensions'
as $$
declare
  v_target date:=(date_trunc('month',timezone('Europe/Vilnius',now()))+interval '1 month')::date;
  v_year integer:=extract(year from v_target)::integer;
  v_month integer:=extract(month from v_target)::integer;
  v_zero jsonb; v_phase jsonb;
begin
  if now()>=public.preference_cutoff_v2595(v_year,v_month) then
    v_zero:=public.auto_submit_due_zero_preferences_v2595();
  end if;
  v_phase:=public.sync_schedule_cycle_v25119(v_year,v_month);
  return jsonb_build_object('ok',true,'year',v_year,'month',v_month,'phase',v_phase,'zero_preferences',v_zero);
end;
$$;

-- Existing October claim was created under the old pre-FCFS logic; user confirmed
-- October dubliai have NOT yet been chosen. Start the October FCFS board clean.
delete from public.weekend_backup_claims where year=2026 and month=10;

-- Backfill current October submissions so they earn points for NOVEMBER priority.
with ranked as (
  select p.year,p.month,p.initials,p.submitted_at,p.submission_source,
         row_number() over(partition by p.year,p.month order by p.submitted_at,p.initials)::integer rn
  from public.preferences p
  where p.year=2026 and p.month=10 and p.submission_source<>'deadline_zero'
)
insert into public.preference_priority_points_v25118(year,month,initials,first_submitted_at,submission_order,points_awarded,source)
select year,month,initials,submitted_at,rn,greatest(0,17-rn),submission_source from ranked
on conflict(year,month,initials) do nothing;

-- Replace/create the periodic job.
do $$
declare v_job integer;
begin
  select jobid into v_job from cron.job where jobname='v25119-auto-cycle-5min' limit 1;
  if v_job is not null then perform cron.unschedule(v_job); end if;
  perform cron.schedule('v25119-auto-cycle-5min','*/5 * * * *','select public.auto_advance_scheduler_cycle_v25119();');
end $$;
