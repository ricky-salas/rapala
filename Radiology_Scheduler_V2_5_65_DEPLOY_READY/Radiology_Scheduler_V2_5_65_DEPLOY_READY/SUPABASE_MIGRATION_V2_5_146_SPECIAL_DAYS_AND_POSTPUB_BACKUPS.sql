-- V2.5.146 — SPECIALIOS DIENOS + POST-PUBLICATION DUBLIAI
-- 1) Preferences no longer save/erase paid special workdays.
-- 2) Paid wellness / qualification days stay in their own table and lock at SYSTEM publication.
-- 3) Weekend dubliai self-service + operator override unlock ONLY after SYSTEM is published.
--    From Oct-2026 the active catalog is one FULL 12 h position per weekend duty day.

-- Restore the current preference RPCs without coupling them to the Specialios dienos table.
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

-- Dubliai become an operational layer: no self-selection before publication.
create or replace function public.claim_weekend_backup_fcfs_v25118(
  p_year integer,p_month integer,p_covered_slot integer,p_day integer,p_block text
)
returns public.weekend_backup_claims
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid(); v_initials text; v_close timestamptz;
  v_existing public.weekend_backup_claims%rowtype; v_owner public.weekend_backup_claims%rowtype;
  v_count integer; v_row public.weekend_backup_claims%rowtype;
begin
  if (p_year*100+p_month)<202610 then raise exception 'FCFS_BACKUP_MODE_NOT_ACTIVE'; end if;
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select initials into v_initials from public.user_profiles where user_id=v_uid and approved=true limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'BACKUP_ONLY_AFTER_PUBLICATION'; end if;
  v_close:=public.backup_self_service_close_v25136(p_year,p_month);
  if now()>=v_close then raise exception 'BACKUP_WINDOW_CLOSED'; end if;
  if not exists(select 1 from public.weekend_backup_slot_catalog_v25119 c
                where c.year=p_year and c.month=p_month and c.covered_slot=p_covered_slot
                  and c.claim_day=p_day and c.claim_block=p_block and c.active=true)
    then raise exception 'BACKUP_SLOT_OUTSIDE_ACTIVE_CATALOG'; end if;
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
  values(p_year,p_month,p_covered_slot,v_initials,'self_fcfs_postpub',now(),now(),p_day,p_block) returning * into v_row;
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
  if not exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'BACKUP_ONLY_AFTER_PUBLICATION'; end if;
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

-- Operator override follows the same publication gate.
create or replace function public.operator_set_weekend_backup_v25119(
  p_year integer,p_month integer,p_target_initials text,p_covered_slot integer,p_reason text
)
returns jsonb
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_actor text; v_target public.weekend_backup_claims%rowtype; v_owner public.weekend_backup_claims%rowtype;
  v_slot public.weekend_backup_slot_catalog_v25119%rowtype;
  v_old_slot public.weekend_backup_slot_catalog_v25119%rowtype;
  v_before jsonb; v_after jsonb;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then raise exception 'LIFECYCLE_OPERATOR_REQUIRED'; end if;
  select initials into v_actor from public.user_profiles where user_id=auth.uid() and approved=true limit 1;
  if v_actor is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;
  if not exists(select 1 from public.schedules s where s.year=p_year and s.month=p_month and s.status='published')
    then raise exception 'BACKUP_ONLY_AFTER_PUBLICATION'; end if;
  if coalesce(trim(p_reason),'')='' then raise exception 'BACKUP_OVERRIDE_REASON_REQUIRED'; end if;
  if not exists(select 1 from public.resident_directory where initials=p_target_initials and coalesce(active,true)=true)
    then raise exception 'UNKNOWN_OR_INACTIVE_RESIDENT'; end if;
  select * into v_slot from public.weekend_backup_slot_catalog_v25119
    where year=p_year and month=p_month and covered_slot=p_covered_slot and active=true;
  if not found then raise exception 'BACKUP_SLOT_OUTSIDE_ACTIVE_CATALOG'; end if;
  perform pg_advisory_xact_lock(25121,p_year*100+p_month);
  select * into v_target from public.weekend_backup_claims
    where year=p_year and month=p_month and initials=p_target_initials for update;
  select * into v_owner from public.weekend_backup_claims
    where year=p_year and month=p_month and covered_slot=p_covered_slot for update;
  v_before:=jsonb_build_object('target',to_jsonb(v_target),'slot_owner',to_jsonb(v_owner));
  if v_owner.id is not null and v_owner.initials is distinct from p_target_initials then
    if v_target.id is null then raise exception 'TARGET_SLOT_ALREADY_OWNED'; end if;
    select * into v_old_slot from public.weekend_backup_slot_catalog_v25119
      where year=p_year and month=p_month and covered_slot=v_target.covered_slot and active=true;
    if v_old_slot.covered_slot is null then raise exception 'TARGET_OLD_SLOT_NOT_IN_CATALOG'; end if;
    update public.weekend_backup_claims
      set covered_slot=v_old_slot.covered_slot,claim_day=v_old_slot.claim_day,claim_block=v_old_slot.claim_block,
          source='operator_manual_swap_postpub',updated_at=now()
      where id=v_owner.id;
  end if;
  if v_target.id is null then
    insert into public.weekend_backup_claims(year,month,covered_slot,initials,source,claimed_at,updated_at,claim_day,claim_block)
    values(p_year,p_month,v_slot.covered_slot,p_target_initials,'operator_manual_postpub',now(),now(),v_slot.claim_day,v_slot.claim_block);
  else
    update public.weekend_backup_claims
      set covered_slot=v_slot.covered_slot,claim_day=v_slot.claim_day,claim_block=v_slot.claim_block,
          source='operator_manual_postpub',updated_at=now()
      where id=v_target.id;
  end if;
  select jsonb_build_object(
    'target',(select to_jsonb(w) from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.initials=p_target_initials),
    'slot_owner',(select to_jsonb(w) from public.weekend_backup_claims w where w.year=p_year and w.month=p_month and w.covered_slot=p_covered_slot)
  ) into v_after;
  insert into public.weekend_backup_override_audit_v25119(year,month,target_initials,actor_user_id,actor_initials,reason,before_json,after_json)
  values(p_year,p_month,p_target_initials,auth.uid(),v_actor,trim(p_reason),v_before,v_after);
  return jsonb_build_object('ok',true,'before',v_before,'after',v_after);
end;
$$;
grant execute on function public.operator_set_weekend_backup_v25119(integer,integer,text,integer,text) to authenticated;
