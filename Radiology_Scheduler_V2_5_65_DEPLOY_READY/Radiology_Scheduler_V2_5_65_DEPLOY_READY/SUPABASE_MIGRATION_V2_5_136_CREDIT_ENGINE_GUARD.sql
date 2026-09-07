-- V2.5.136 — coefficient reward-credit wallet + all-month dubliai + anti-gaming ranking guard
-- Apply after the migrations included in V2.5.135.

-- ---------------------------------------------------------------------------
-- 1) Reward credit wallet
-- Internal unit = one weighted tariff-hour. 12 units = 1.00 user-facing credit.
-- The app calculates the LSMU 1x / 2x / 3x hourly value from the actual shift time.
-- ---------------------------------------------------------------------------
create table if not exists public.reward_credit_ledger_v25136 (
  id bigserial primary key,
  initials text not null references public.resident_directory(initials) on update cascade,
  units integer not null check (units > 0),
  source text not null,
  source_backup_id bigint,
  event_date date,
  shift_kind text,
  detail text not null default '',
  created_at timestamptz not null default now(),
  created_by uuid default auth.uid()
);

create unique index if not exists reward_credit_ledger_v25136_backup_uidx
on public.reward_credit_ledger_v25136(source_backup_id)
where source_backup_id is not null;

create table if not exists public.reward_credit_redemptions_v25136 (
  year integer not null,
  month integer not null check (month between 1 and 12),
  initials text not null references public.resident_directory(initials) on update cascade,
  units integer not null default 0 check (units >= 0),
  status text not null default 'reserved' check (status in ('reserved','consumed','cancelled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  consumed_at timestamptz,
  primary key (year,month,initials)
);

alter table public.reward_credit_ledger_v25136 enable row level security;
alter table public.reward_credit_redemptions_v25136 enable row level security;

drop policy if exists "reward credit ledger read" on public.reward_credit_ledger_v25136;
create policy "reward credit ledger read"
on public.reward_credit_ledger_v25136 for select to authenticated
using (
  initials=(select up.initials from public.user_profiles up where up.user_id=auth.uid() and up.approved=true limit 1)
  or public.is_lifecycle_operator_v2592(auth.uid())
);

drop policy if exists "reward credit redemption read" on public.reward_credit_redemptions_v25136;
create policy "reward credit redemption read"
on public.reward_credit_redemptions_v25136 for select to authenticated
using (
  initials=(select up.initials from public.user_profiles up where up.user_id=auth.uid() and up.approved=true limit 1)
  or public.is_lifecycle_operator_v2592(auth.uid())
);

revoke insert,update,delete on public.reward_credit_ledger_v25136 from authenticated,anon;
revoke insert,update,delete on public.reward_credit_redemptions_v25136 from authenticated,anon;
grant select on public.reward_credit_ledger_v25136 to authenticated;
grant select on public.reward_credit_redemptions_v25136 to authenticated;

-- Carry forward any still-unused legacy credits once. AM/PM = 6 weighted hours;
-- legacy NIGHT = normal 20:00-08:00 = 20 weighted hours.
insert into public.reward_credit_ledger_v25136(initials,units,source,source_backup_id,shift_kind,detail,created_at)
select e.initials,
       case upper(coalesce(e.credit_type,'')) when 'AM' then 6 when 'PM' then 6 when 'NIGHT' then 20
            else greatest(1,coalesce(e.cover_hours,6)) end,
       'legacy_v2598',e.source_backup_id,upper(coalesce(e.credit_type,'')),
       'Perkelta iš ankstesnio poilsio kreditų banko',coalesce(e.created_at,now())
from public.backup_credit_earnings e
where e.redeemed_at is null and e.consumed_at is null
on conflict do nothing;

create or replace function public.complete_backup_cover_v25136(
  p_backup_id bigint,p_credit_units integer,p_shift_kind text,p_event_date date
)
returns jsonb
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  b public.backup_assignments%rowtype;
  v_coverer text;
  v_id bigint;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  if p_credit_units<=0 or p_credit_units>96 then raise exception 'INVALID_CREDIT_UNITS'; end if;
  if upper(coalesce(p_shift_kind,'')) not in ('AM','PM','NIGHT') then raise exception 'UNSUPPORTED_CREDIT_SHIFT'; end if;

  select * into b from public.backup_assignments where id=p_backup_id for update;
  if not found then raise exception 'BACKUP_NOT_FOUND'; end if;
  if b.completed_at is not null then raise exception 'BACKUP_ALREADY_COMPLETED'; end if;
  v_coverer:=coalesce(b.actual_backup,b.planned_backup);
  if v_coverer is null then raise exception 'BACKUP_HAS_NO_COVERER'; end if;

  insert into public.reward_credit_ledger_v25136(
    initials,units,source,source_backup_id,event_date,shift_kind,detail,created_by
  ) values (
    v_coverer,p_credit_units,'completed_backup',p_backup_id,p_event_date,
    upper(p_shift_kind),'Realus pavadavimas',auth.uid()
  ) returning id into v_id;

  update public.backup_assignments
  set completed_at=now(),completed_by=auth.uid(),updated_at=now()
  where id=p_backup_id;

  return jsonb_build_object('coverer',v_coverer,'credit_units',p_credit_units,'credit_id',v_id);
end;
$$;
grant execute on function public.complete_backup_cover_v25136(bigint,integer,text,date) to authenticated;

create or replace function public.undo_backup_credit_v25136(p_backup_id bigint)
returns void
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_initials text;
  v_units integer;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  select initials,units into v_initials,v_units
  from public.reward_credit_ledger_v25136 where source_backup_id=p_backup_id for update;
  if found then
    -- Do not allow undo if this would make the resident overdrawn after reserved/consumed redemptions.
    if (select coalesce(sum(units),0) from public.reward_credit_ledger_v25136 where initials=v_initials)
       - v_units
       < (select coalesce(sum(units),0) from public.reward_credit_redemptions_v25136 where initials=v_initials and status in ('reserved','consumed'))
    then raise exception 'CANNOT_UNDO_CREDIT_ALREADY_RESERVED_OR_USED'; end if;
    delete from public.reward_credit_ledger_v25136 where source_backup_id=p_backup_id;
  end if;
  update public.backup_assignments set completed_at=null,completed_by=null,updated_at=now() where id=p_backup_id;
end;
$$;
grant execute on function public.undo_backup_credit_v25136(bigint) to authenticated;

create or replace function public.award_manual_reward_credit_v25136(
  p_target_initials text,p_event_date date,p_shift_kind text,p_units integer,p_detail text default ''
)
returns jsonb
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_id bigint;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory where initials=p_target_initials and coalesce(active,true)=true)
    then raise exception 'UNKNOWN_OR_INACTIVE_RESIDENT'; end if;
  if p_units<=0 or p_units>96 then raise exception 'INVALID_CREDIT_UNITS'; end if;
  if upper(coalesce(p_shift_kind,'')) not in ('AM','PM','FULL','NIGHT') then raise exception 'UNSUPPORTED_CREDIT_SHIFT'; end if;
  insert into public.reward_credit_ledger_v25136(initials,units,source,event_date,shift_kind,detail,created_by)
  values(p_target_initials,p_units,'manual_emergency_cover',p_event_date,upper(p_shift_kind),coalesce(p_detail,''),auth.uid())
  returning id into v_id;
  return jsonb_build_object('id',v_id,'initials',p_target_initials,'units',p_units);
end;
$$;
grant execute on function public.award_manual_reward_credit_v25136(text,date,text,integer,text) to authenticated;

create or replace function public.set_my_reward_credit_redemption_v25136(
  p_year integer,p_month integer,p_units integer
)
returns jsonb
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_initials text;
  v_earned integer;
  v_other_reserved integer;
begin
  select up.initials into v_initials from public.user_profiles up
  where up.user_id=auth.uid() and up.approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if p_units<0 or mod(p_units,6)<>0 then raise exception 'CREDIT_REDEMPTION_MUST_USE_HALF_CREDIT_STEPS'; end if;
  -- Architecture choice for V2.5.136: credits are chosen before the preliminary SYSTEM is published.
  if exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published' and s.current_json is not null)
     or exists(select 1 from public.schedule_lifecycle l where l.year=p_year and l.month=p_month and l.state='final')
  then raise exception 'CREDIT_REDEMPTION_LOCKED_AFTER_PRELIMINARY'; end if;

  -- Credits earned during the target month become usable only from the NEXT month.
  select coalesce(sum(units),0)::integer into v_earned
  from public.reward_credit_ledger_v25136
  where initials=v_initials
    and (
      event_date < make_date(p_year,p_month,1)
      or (event_date is null and created_at < (make_date(p_year,p_month,1)::timestamp at time zone 'Europe/Vilnius'))
    );
  select coalesce(sum(units),0)::integer into v_other_reserved
  from public.reward_credit_redemptions_v25136
  where initials=v_initials and status in ('reserved','consumed') and not (year=p_year and month=p_month);
  if p_units > greatest(0,v_earned-v_other_reserved) then raise exception 'INSUFFICIENT_REWARD_CREDITS'; end if;

  if p_units=0 then
    delete from public.reward_credit_redemptions_v25136
    where year=p_year and month=p_month and initials=v_initials and status='reserved';
  else
    insert into public.reward_credit_redemptions_v25136(year,month,initials,units,status,updated_at)
    values(p_year,p_month,v_initials,p_units,'reserved',now())
    on conflict(year,month,initials) do update set units=excluded.units,status='reserved',updated_at=now(),consumed_at=null;
  end if;
  return jsonb_build_object('initials',v_initials,'year',p_year,'month',p_month,'units',p_units);
end;
$$;
grant execute on function public.set_my_reward_credit_redemption_v25136(integer,integer,integer) to authenticated;

create or replace function public.consume_reward_credit_redemptions_v25136(p_year integer,p_month integer)
returns jsonb
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_n integer;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  update public.reward_credit_redemptions_v25136
  set status='consumed',consumed_at=coalesce(consumed_at,now()),updated_at=now()
  where year=p_year and month=p_month and status='reserved';
  get diagnostics v_n=row_count;
  return jsonb_build_object('consumed_rows',v_n);
end;
$$;
grant execute on function public.consume_reward_credit_redemptions_v25136(integer,integer) to authenticated;

-- ---------------------------------------------------------------------------
-- 2) Submission-integrity guard
-- Ranking belongs only to concrete MONTHLY wishes ("Noriu laisvos" / "Pageidauju dirbti").
-- A resident who submits no such wishes is recorded as submitted but occupies no rank.
-- If rankable wishes are added later, the rank starts at that later material submission.
-- Priority is based on the LAST material change, not the first click. There is no
-- grace period that preserves an early place after a real schedule-affecting edit.
-- Dubliai, credit-wallet choices and free-text notes do not create or reset this rank.
-- Hard availability / leave / safety facts do not create a rank by themselves, but if
-- the resident already has a rankable monthly wish, changing those schedule constraints
-- also refreshes the material timestamp. This prevents day-1 placeholder gaming.
-- ---------------------------------------------------------------------------
alter table public.preference_priority_points_v25118
  add column if not exists priority_fingerprint text,
  add column if not exists last_material_change_at timestamptz,
  add column if not exists priority_started_at timestamptz,
  add column if not exists revision_count integer not null default 0;

create or replace function public._preference_has_rankable_wishes_v25136(p_payload jsonb)
returns boolean
language sql immutable
set search_path to 'public'
as $$
  select
    jsonb_array_length(coalesce(p_payload->'soft_free','[]'::jsonb)) > 0
    or jsonb_array_length(coalesce(p_payload->'soft_free_am','[]'::jsonb)) > 0
    or jsonb_array_length(coalesce(p_payload->'soft_free_pm','[]'::jsonb)) > 0
    or jsonb_array_length(coalesce(p_payload->'preferred','[]'::jsonb)) > 0
    or jsonb_array_length(coalesce(p_payload->'preferred_am','[]'::jsonb)) > 0
    or jsonb_array_length(coalesce(p_payload->'preferred_pm','[]'::jsonb)) > 0
$$;

create or replace function public._preference_priority_fingerprint_v25136(p_payload jsonb)
returns text
language sql immutable
set search_path to 'public'
as $$
  select md5(jsonb_build_object(
    'unavailable',coalesce(p_payload->'unavailable','[]'::jsonb),
    'unavailable_am',coalesce(p_payload->'unavailable_am','[]'::jsonb),
    'unavailable_pm',coalesce(p_payload->'unavailable_pm','[]'::jsonb),
    'justified_absence',coalesce(p_payload->'justified_absence','[]'::jsonb),
    'vacation',coalesce(p_payload->'vacation','[]'::jsonb),
    'long_duty',coalesce(p_payload->'long_duty','[]'::jsonb),
    'soft_free',coalesce(p_payload->'soft_free','[]'::jsonb),
    'soft_free_am',coalesce(p_payload->'soft_free_am','[]'::jsonb),
    'soft_free_pm',coalesce(p_payload->'soft_free_pm','[]'::jsonb),
    'preferred',coalesce(p_payload->'preferred','[]'::jsonb),
    'preferred_am',coalesce(p_payload->'preferred_am','[]'::jsonb),
    'preferred_pm',coalesce(p_payload->'preferred_pm','[]'::jsonb)
  )::text)
$$;

-- Seed existing rows. Existing empty/hard-only submissions lose their rank because
-- there is no tie-breaking wish to prioritize; ranked rows are compacted below.
update public.preference_priority_points_v25118 q
set priority_fingerprint=public._preference_priority_fingerprint_v25136(jsonb_build_object(
      'unavailable',coalesce(to_jsonb(p.unavailable),'[]'::jsonb),
      'unavailable_am',coalesce(to_jsonb(p.unavailable_am),'[]'::jsonb),
      'unavailable_pm',coalesce(to_jsonb(p.unavailable_pm),'[]'::jsonb),
      'justified_absence',coalesce(to_jsonb(p.justified_absence),'[]'::jsonb),
      'vacation',coalesce(to_jsonb(p.vacation),'[]'::jsonb),
      'long_duty',coalesce(to_jsonb(p.long_duty),'[]'::jsonb),
      'soft_free',coalesce(to_jsonb(p.soft_free),'[]'::jsonb),
      'soft_free_am',coalesce(to_jsonb(p.soft_free_am),'[]'::jsonb),
      'soft_free_pm',coalesce(to_jsonb(p.soft_free_pm),'[]'::jsonb),
      'preferred',coalesce(to_jsonb(p.preferred),'[]'::jsonb),
      'preferred_am',coalesce(to_jsonb(p.preferred_am),'[]'::jsonb),
      'preferred_pm',coalesce(to_jsonb(p.preferred_pm),'[]'::jsonb)
    )),
    last_material_change_at=coalesce(q.last_material_change_at,q.first_submitted_at),
    priority_started_at=coalesce(q.priority_started_at,q.first_submitted_at)
from public.preferences p
where p.year=q.year and p.month=q.month and p.initials=q.initials;

update public.preference_priority_points_v25118 q
set submission_order=null,points_awarded=0,source='no_rankable_wishes'
from public.preferences p
where p.year=q.year and p.month=q.month and p.initials=q.initials
  and not public._preference_has_rankable_wishes_v25136(jsonb_build_object(
      'soft_free',coalesce(to_jsonb(p.soft_free),'[]'::jsonb),
      'soft_free_am',coalesce(to_jsonb(p.soft_free_am),'[]'::jsonb),
      'soft_free_pm',coalesce(to_jsonb(p.soft_free_pm),'[]'::jsonb),
      'preferred',coalesce(to_jsonb(p.preferred),'[]'::jsonb),
      'preferred_am',coalesce(to_jsonb(p.preferred_am),'[]'::jsonb),
      'preferred_pm',coalesce(to_jsonb(p.preferred_pm),'[]'::jsonb)
  ));

-- Compact any surviving ranks deterministically after removing no-wish rows.
with ranked as (
  select year,month,initials,
         row_number() over(partition by year,month order by submission_order,first_submitted_at,initials)::integer as new_order
  from public.preference_priority_points_v25118
  where submission_order is not null
)
update public.preference_priority_points_v25118 q
set submission_order=r.new_order,points_awarded=greatest(0,17-r.new_order)
from ranked r
where q.year=r.year and q.month=r.month and q.initials=r.initials;

create or replace function public._apply_preference_integrity_guard_v25136(
  p_year integer,p_month integer,p_initials text,p_payload jsonb,p_source text
)
returns void
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_old public.preference_priority_points_v25118%rowtype;
  v_fp text;
  v_has_rankable boolean;
  v_old_order integer;
  v_new_order integer;
begin
  if (p_year*100+p_month)<202610 then return; end if;
  v_fp:=public._preference_priority_fingerprint_v25136(coalesce(p_payload,'{}'::jsonb));
  v_has_rankable:=public._preference_has_rankable_wishes_v25136(coalesce(p_payload,'{}'::jsonb));
  perform pg_advisory_xact_lock(25136,p_year*100+p_month);

  select * into v_old from public.preference_priority_points_v25118
  where year=p_year and month=p_month and initials=p_initials for update;

  if not found then
    if v_has_rankable and coalesce(p_source,'')<>'deadline_zero' then
      perform public._register_preference_priority_v25118(p_year,p_month,p_initials,p_source);
      update public.preference_priority_points_v25118
      set priority_fingerprint=v_fp,last_material_change_at=now(),priority_started_at=now()
      where year=p_year and month=p_month and initials=p_initials;
    else
      insert into public.preference_priority_points_v25118(
        year,month,initials,first_submitted_at,submission_order,points_awarded,source,
        priority_fingerprint,last_material_change_at,priority_started_at,revision_count
      ) values (
        p_year,p_month,p_initials,now(),null,0,
        case when coalesce(p_source,'')='deadline_zero' then 'deadline_zero' else 'no_rankable_wishes' end,
        v_fp,now(),null,0
      );
    end if;
    return;
  end if;

  -- No concrete monthly wish = no place in the tie-break queue. If a resident
  -- removes all rankable wishes, release the old place immediately and compact.
  if not v_has_rankable then
    v_old_order:=v_old.submission_order;
    update public.preference_priority_points_v25118
    set submission_order=null,points_awarded=0,source=case when coalesce(p_source,'')='deadline_zero' then 'deadline_zero' else 'no_rankable_wishes' end,
        priority_fingerprint=v_fp,last_material_change_at=now(),revision_count=revision_count+1
    where year=p_year and month=p_month and initials=p_initials;
    if v_old_order is not null then
      update public.preference_priority_points_v25118
      set submission_order=submission_order-1
      where year=p_year and month=p_month and submission_order>v_old_order;
      update public.preference_priority_points_v25118
      set points_awarded=greatest(0,17-submission_order)
      where year=p_year and month=p_month and submission_order is not null;
    end if;
    return;
  end if;

  -- A previously neutral/empty submission becomes ranked only NOW, when a real
  -- monthly wish is first added. This is the anti-placeholder rule.
  if v_old.submission_order is null then
    select coalesce(max(submission_order),0)+1 into v_new_order
    from public.preference_priority_points_v25118 where year=p_year and month=p_month;
    update public.preference_priority_points_v25118
    set submission_order=v_new_order,points_awarded=greatest(0,17-v_new_order),source=coalesce(nullif(p_source,''),'resident'),
        priority_fingerprint=v_fp,last_material_change_at=now(),priority_started_at=now(),revision_count=revision_count+1
    where year=p_year and month=p_month and initials=p_initials;
    return;
  end if;

  if v_old.priority_fingerprint is not distinct from v_fp then return; end if;

  v_old_order:=v_old.submission_order;
  if v_old_order is null then return; end if;

  -- Any material edit refreshes priority time: remove this resident, compact
  -- everyone after them, then append the changed version to the current queue.
  update public.preference_priority_points_v25118
  set submission_order=null,points_awarded=0
  where year=p_year and month=p_month and initials=p_initials;

  update public.preference_priority_points_v25118
  set submission_order=submission_order-1
  where year=p_year and month=p_month and submission_order>v_old_order;

  select coalesce(max(submission_order),0)+1 into v_new_order
  from public.preference_priority_points_v25118 where year=p_year and month=p_month;
  update public.preference_priority_points_v25118
  set submission_order=v_new_order,points_awarded=greatest(0,17-v_new_order),source=coalesce(nullif(p_source,''),source),
      priority_fingerprint=v_fp,last_material_change_at=now(),revision_count=revision_count+1
  where year=p_year and month=p_month and initials=p_initials;

  update public.preference_priority_points_v25118
  set points_awarded=greatest(0,17-submission_order)
  where year=p_year and month=p_month and submission_order is not null;
end;
$$;
revoke all on function public._apply_preference_integrity_guard_v25136(integer,integer,text,jsonb,text) from public;

-- Re-wrap the resident save with the integrity guard.
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
  perform public._apply_preference_integrity_guard_v25136(p_year,p_month,v_initials,coalesce(p_payload,'{}'::jsonb),'resident');
  return v_row;
end;
$$;

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
  perform public._apply_preference_integrity_guard_v25136(p_year,p_month,p_target_initials,coalesce(p_payload,'{}'::jsonb),'operator_manual');
  insert into public.preference_operator_audit(year,month,target_initials,actor_user_id,actor_initials,reason,before_json,after_json)
  values(p_year,p_month,p_target_initials,v_uid,v_actor,trim(p_reason),v_before,to_jsonb(v_row));
  return v_row;
end;
$$;

-- ---------------------------------------------------------------------------
-- 3) Dubliai self-service independent from schedule status, open through target month.
-- Active/completed duties cannot be silently moved.
-- ---------------------------------------------------------------------------
create or replace function public.backup_self_service_close_v25136(p_year integer,p_month integer)
returns timestamptz
language sql immutable
set search_path to 'public'
as $$
  select ((make_date(p_year,p_month,1)+interval '1 month')::timestamp at time zone 'Europe/Vilnius')
$$;

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
  v_close:=public.backup_self_service_close_v25136(p_year,p_month);
  if now()<v_open then raise exception 'BACKUP_WINDOW_NOT_OPEN'; end if;
  if now()>=v_close then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  if not exists(select 1 from public.weekend_backup_slot_catalog_v25119 c
                where c.year=p_year and c.month=p_month and c.covered_slot=p_covered_slot
                  and c.claim_day=p_day and c.claim_block=p_block and c.active=true)
    then raise exception 'BACKUP_SLOT_OUTSIDE_16_SLOT_CATALOG'; end if;
  perform pg_advisory_xact_lock(25119,p_year*100+p_month);
  select * into v_existing from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials for update;
  if found and v_existing.covered_slot=p_covered_slot and v_existing.claim_day=p_day and v_existing.claim_block=p_block then return v_existing; end if;
  if found and exists(select 1 from public.backup_assignments b where b.year=p_year and b.month=p_month and b.covered_slot=v_existing.covered_slot and (b.activated_at is not null or b.completed_at is not null))
    then raise exception 'CURRENT_BACKUP_ALREADY_ACTIVE_OR_COMPLETED'; end if;
  if exists(select 1 from public.backup_assignments b where b.year=p_year and b.month=p_month and b.covered_slot=p_covered_slot and (b.activated_at is not null or b.completed_at is not null))
    then raise exception 'TARGET_BACKUP_ALREADY_ACTIVE_OR_COMPLETED'; end if;
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
declare v_initials text; v_close timestamptz; v_old public.weekend_backup_claims%rowtype;
begin
  select initials into v_initials from public.user_profiles where user_id=auth.uid() and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  v_close:=public.backup_self_service_close_v25136(p_year,p_month);
  if now()>=v_close then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  select * into v_old from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials for update;
  if not found then return false; end if;
  if exists(select 1 from public.backup_assignments b where b.year=p_year and b.month=p_month and b.covered_slot=v_old.covered_slot and (b.activated_at is not null or b.completed_at is not null))
    then raise exception 'CURRENT_BACKUP_ALREADY_ACTIVE_OR_COMPLETED'; end if;
  delete from public.weekend_backup_claims where year=p_year and month=p_month and initials=v_initials;
  return true;
end;
$$;
grant execute on function public.release_weekend_backup_fcfs_v25118(integer,integer) to authenticated;
