-- V2.5.92 — simplified finalization lifecycle + contingency operator + audited manual override

-- R.S. is the primary operator. R.Š. is the contingency/research operator.
-- Identity remains bound by auth.uid(); this only grants capability.
create or replace function public.is_operational_seniune_v2591(uid uuid)
returns boolean
language sql
stable security definer
set search_path to 'public'
as $$
  select exists(
    select 1
    from public.user_profiles up
    where up.user_id=uid
      and up.approved=true
      and up.initials in ('R.S.','R.Š.')
  );
$$;

create or replace function public.is_lifecycle_operator_v2592(uid uuid)
returns boolean
language sql
stable security definer
set search_path to 'public'
as $$
  select public.is_operational_seniune_v2591(uid);
$$;

-- Keep the role-based rule-admin helper aligned with the already locked
-- is_senior(auth.uid()) privilege model (R.S. + embedded R.Š., never identity switching).
create or replace function public.scheduler_rule_admin_v2534()
returns boolean
language sql
stable security definer
set search_path to 'public'
as $$
  select public.is_senior(auth.uid());
$$;

-- Private operator-working phase: SYSTEM is frozen, ACTUAL may be manually corrected,
-- but no resident preliminary/swap email has been sent yet.
alter table public.schedule_lifecycle drop constraint if exists schedule_lifecycle_state_check;
alter table public.schedule_lifecycle
  add constraint schedule_lifecycle_state_check
  check (state in ('draft','working','swap_open','swap_closed','final'));

create table if not exists public.manual_schedule_overrides (
  id bigserial primary key,
  year integer not null,
  month integer not null check (month between 1 and 12),
  slot_a integer not null,
  slot_b integer not null,
  person_a text not null references public.resident_directory(initials),
  person_b text not null references public.resident_directory(initials),
  reason text not null default '',
  actor_user_id uuid not null,
  actor_initials text not null references public.resident_directory(initials),
  created_at timestamptz not null default now()
);
alter table public.manual_schedule_overrides enable row level security;
drop policy if exists "manual overrides operator read" on public.manual_schedule_overrides;
create policy "manual overrides operator read" on public.manual_schedule_overrides
for select to authenticated using (public.is_lifecycle_operator_v2592(auth.uid()));

create or replace function public.ensure_working_schedule_v2592(p_year integer,p_month integer)
returns public.schedule_lifecycle
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare v_row public.schedule_lifecycle%rowtype; v_state text;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  if not exists(
    select 1 from public.schedules s
    where s.year=p_year and s.month=p_month and s.status='published'
      and s.baseline_json is not null and s.current_json is not null
  ) then raise exception 'PUBLISHED_SYSTEM_REQUIRED'; end if;

  select state into v_state from public.schedule_lifecycle where year=p_year and month=p_month for update;
  if v_state='final' then raise exception 'FINAL_SCHEDULE_IMMUTABLE'; end if;
  if v_state is null then
    insert into public.schedule_lifecycle(year,month,state,updated_at)
    values(p_year,p_month,'working',now()) returning * into v_row;
  elsif v_state='draft' then
    update public.schedule_lifecycle set state='working',updated_at=now()
    where year=p_year and month=p_month returning * into v_row;
  else
    select * into v_row from public.schedule_lifecycle where year=p_year and month=p_month;
  end if;
  return v_row;
end;
$$;

create or replace function public.apply_manual_schedule_override_v2592(
  p_year integer,p_month integer,p_current_json jsonb,
  p_slot_a integer,p_slot_b integer,p_person_a text,p_person_b text,p_reason text default ''
)
returns public.manual_schedule_overrides
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare v_actor text; v_state text; v_row public.manual_schedule_overrides%rowtype;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  select initials into v_actor from public.user_profiles where user_id=auth.uid() and approved=true limit 1;
  if v_actor is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if p_slot_a=p_slot_b or p_person_a=p_person_b then raise exception 'INVALID_MANUAL_SWAP'; end if;
  if coalesce(trim(p_reason),'')='' then raise exception 'MANUAL_OVERRIDE_REASON_REQUIRED'; end if;

  if not exists(
    select 1 from public.schedules s
    where s.year=p_year and s.month=p_month and s.status='published'
      and s.baseline_json is not null and s.current_json is not null
  ) then raise exception 'PUBLISHED_SYSTEM_REQUIRED'; end if;

  select state into v_state from public.schedule_lifecycle where year=p_year and month=p_month for update;
  if v_state='final' then raise exception 'FINAL_SCHEDULE_IMMUTABLE'; end if;
  if v_state is null then
    insert into public.schedule_lifecycle(year,month,state,updated_at)
    values(p_year,p_month,'working',now());
  elsif v_state='draft' then
    update public.schedule_lifecycle set state='working',updated_at=now()
    where year=p_year and month=p_month;
  end if;

  update public.schedules
  set current_json=p_current_json,updated_at=now()
  where year=p_year and month=p_month and status='published';
  if not found then raise exception 'PUBLISHED_SYSTEM_REQUIRED'; end if;

  -- A direct operator correction supersedes unresolved resident requests that
  -- depend on either changed slot. Already-applied swap history remains intact.
  update public.swap_requests
  set status='rejected',
      reason=jsonb_build_object(
        'kind','operator_override','phase','superseded',
        'actor',v_actor,'at',now(),'note','slot changed by operator manual override'
      )::text
  where year=p_year and month=p_month
    and (slot_a in (p_slot_a,p_slot_b) or slot_b in (p_slot_a,p_slot_b))
    and (
      status='pending'
      or (status='approved' and coalesce(reason,'') like '%accepted_pending_senior_apply%')
    );

  update public.backup_swap_requests
  set status='rejected',note=concat_ws(' | ',nullif(note,''),'superseded by operator manual override')
  where year=p_year and month=p_month
    and (requester_slot in (p_slot_a,p_slot_b) or target_slot in (p_slot_a,p_slot_b))
    and status='pending';

  insert into public.manual_schedule_overrides(
    year,month,slot_a,slot_b,person_a,person_b,reason,actor_user_id,actor_initials
  ) values(
    p_year,p_month,p_slot_a,p_slot_b,p_person_a,p_person_b,trim(p_reason),auth.uid(),v_actor
  ) returning * into v_row;
  return v_row;
end;
$$;

-- Finalization may intentionally skip the preliminary resident-swap phase.
-- It also may close an active window early when the operator explicitly confirms FINAL.
create or replace function public.finalization_blockers_v2591(p_year integer,p_month integer)
returns jsonb
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare v_state text; a int; b int; c int; d int; v_published boolean;
begin
  select state into v_state from public.schedule_lifecycle where year=p_year and month=p_month;
  select exists(select 1 from public.schedules where year=p_year and month=p_month and status='published' and current_json is not null) into v_published;
  select count(*) into a from public.swap_requests where year=p_year and month=p_month and status='pending';
  select count(*) into b from public.swap_requests where year=p_year and month=p_month and status='approved' and coalesce(reason,'') like '%accepted_pending_senior_apply%';
  select count(*) into c from public.backup_swap_requests where year=p_year and month=p_month and status='pending';
  select count(*) into d from public.late_swap_access where year=p_year and month=p_month and revoked_at is null and expires_at>now() and requests_used<max_requests;
  return jsonb_build_object(
    'state',coalesce(v_state,case when v_published then 'working' else 'draft' end),
    'pending_normal',a,'waiting_senior_apply',b,'pending_backup',c,'active_late_grants',d,
    'clear',(v_published and coalesce(v_state,'working')<>'final' and a=0 and b=0 and c=0 and d=0)
  );
end;
$$;

create or replace function public.finalize_schedule_v2592(p_year integer,p_month integer,p_final_json jsonb)
returns public.schedule_lifecycle
language plpgsql
security definer
set search_path to 'public','auth'
as $$
declare v_row public.schedule_lifecycle%rowtype; v_state text;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  if not exists(
    select 1 from public.schedules s
    where s.year=p_year and s.month=p_month and s.status='published'
      and s.baseline_json is not null and s.current_json is not null
  ) then raise exception 'PUBLISHED_SYSTEM_REQUIRED'; end if;

  select state into v_state from public.schedule_lifecycle where year=p_year and month=p_month for update;
  if v_state is null then
    insert into public.schedule_lifecycle(year,month,state,updated_at)
    values(p_year,p_month,'working',now());
    v_state:='working';
  end if;
  if v_state='final' then raise exception 'FINAL_SCHEDULE_IMMUTABLE'; end if;

  if exists(select 1 from public.late_swap_access where year=p_year and month=p_month and revoked_at is null and expires_at>now() and requests_used<max_requests)
    then raise exception 'ACTIVE_LATE_SWAP_ACCESS_EXISTS'; end if;
  if exists(select 1 from public.swap_requests where year=p_year and month=p_month and status='pending')
    then raise exception 'PENDING_SWAP_REQUESTS_EXIST'; end if;
  if exists(select 1 from public.swap_requests where year=p_year and month=p_month and status='approved' and coalesce(reason,'') like '%accepted_pending_senior_apply%')
    then raise exception 'SWAPS_AWAITING_OPERATOR_APPLY'; end if;
  if exists(select 1 from public.backup_swap_requests where year=p_year and month=p_month and status='pending')
    then raise exception 'PENDING_BACKUP_SWAP_REQUESTS_EXIST'; end if;

  update public.schedule_lifecycle
  set state='final',
      swap_closed_at=coalesce(swap_closed_at,now()),
      finalized_at=now(),finalized_by=auth.uid(),
      final_json=p_final_json,
      final_backups=coalesce((
        select jsonb_agg(to_jsonb(b) order by b.covered_slot)
        from public.backup_assignments b where b.year=p_year and b.month=p_month
      ),'[]'::jsonb),
      updated_at=now()
  where year=p_year and month=p_month
  returning * into v_row;
  return v_row;
end;
$$;

grant execute on function public.ensure_working_schedule_v2592(integer,integer) to authenticated;
grant execute on function public.apply_manual_schedule_override_v2592(integer,integer,jsonb,integer,integer,text,text,text) to authenticated;
grant execute on function public.finalize_schedule_v2592(integer,integer,jsonb) to authenticated;
grant execute on function public.is_lifecycle_operator_v2592(uuid) to authenticated;
