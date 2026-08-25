-- V2.5.86 — Safe DELETE / UNDO for normal swaps, backup swaps and Emergency Rescue.
-- User-visible records are removed after a successful delete/undo, while a separate
-- immutable audit row preserves what was deleted and by whom.

create table if not exists public.schedule_action_deletions (
    id bigserial primary key,
    year integer not null,
    month integer not null check (month between 1 and 12),
    action_type text not null,
    original_table text not null,
    original_id bigint not null,
    original_payload jsonb not null,
    actual_undone boolean not null default false,
    deleted_by uuid references auth.users(id),
    deleted_at timestamptz not null default now()
);

alter table public.schedule_action_deletions enable row level security;
revoke all on table public.schedule_action_deletions from anon, authenticated;

create or replace function public.delete_swap_action_v2586(
    p_request_id bigint,
    p_current_json jsonb default null,
    p_backups jsonb default null
)
returns jsonb
language plpgsql
security definer
set search_path=public
as $$
declare
    r public.swap_requests%rowtype;
    v_caller_initials text;
    v_meta jsonb := '{}'::jsonb;
    v_kind text := '';
    v_phase text := '';
    v_sched public.schedules%rowtype;
    v_assign jsonb;
    v_expected jsonb;
    v_payload jsonb;
    v_item jsonb;
    v_undo boolean := false;
    v_prefix constant text := 'V2555_SWAP_META:';
begin
    select up.initials into v_caller_initials
      from public.user_profiles up
     where up.user_id=auth.uid() and up.approved=true
     limit 1;

    select * into r
      from public.swap_requests
     where id=p_request_id
     for update;

    if not found then
        raise exception 'SWAP_ACTION_NOT_FOUND';
    end if;

    if v_caller_initials is null and not public.is_senior(auth.uid()) then
        raise exception 'APPROVED_USER_REQUIRED';
    end if;

    if v_caller_initials is distinct from r.person_a
       and v_caller_initials is distinct from r.person_b
       and not public.is_senior(auth.uid()) then
        raise exception 'DELETE_SWAP_NOT_AUTHORIZED';
    end if;

    if left(coalesce(r.reason,''),length(v_prefix))=v_prefix then
        begin
            v_meta=substring(r.reason from length(v_prefix)+1)::jsonb;
        exception when others then
            v_meta='{}'::jsonb;
        end;
    end if;
    v_kind=coalesce(v_meta->>'kind','');
    v_phase=coalesce(v_meta->>'phase','');

    -- Only already-applied ACTUAL actions need a schedule rollback.
    v_undo=(v_kind='emergency_rescue' or v_phase='applied');

    if v_undo then
        if p_current_json is null or p_backups is null then
            raise exception 'UNDO_PAYLOAD_REQUIRED';
        end if;
        if jsonb_typeof(p_backups) <> 'array' then
            raise exception 'BACKUP_PLAN_MUST_BE_JSON_ARRAY';
        end if;

        select * into v_sched
          from public.schedules s
         where s.year=r.year and s.month=r.month and s.status='published'
         for update;
        if not found or v_sched.current_json is null then
            raise exception 'PUBLISHED_CURRENT_NOT_FOUND';
        end if;

        v_assign=coalesce(v_sched.current_json->'assignments','{}'::jsonb);

        if v_kind='emergency_rescue' then
            -- Current post-rescue state must still be source vacant + target=mover.
            if (v_assign ? r.slot_a::text) then
                raise exception 'UNDO_RESCUE_STALE_SOURCE: source is no longer vacant';
            end if;
            if (v_assign->>r.slot_b::text) is distinct from r.person_a then
                raise exception 'UNDO_RESCUE_STALE_TARGET: expected %, found %',
                    r.person_a,coalesce(v_assign->>r.slot_b::text,'EMPTY');
            end if;
            v_expected=v_assign
                || jsonb_build_object(r.slot_a::text,r.person_a)
                || jsonb_build_object(r.slot_b::text,r.person_b);
        else
            -- Current post-swap state must still be A's slot=B and B's slot=A.
            if (v_assign->>r.slot_a::text) is distinct from r.person_b
               or (v_assign->>r.slot_b::text) is distinct from r.person_a then
                raise exception 'UNDO_SWAP_STALE: the swapped slots changed again after this action';
            end if;
            v_expected=v_assign
                || jsonb_build_object(r.slot_a::text,r.person_a)
                || jsonb_build_object(r.slot_b::text,r.person_b);
        end if;

        if coalesce(p_current_json->'assignments','{}'::jsonb) is distinct from v_expected then
            raise exception 'UNDO_ASSIGNMENT_PAYLOAD_MISMATCH';
        end if;

        v_payload=coalesce(p_current_json,'{}'::jsonb);
        v_payload=jsonb_set(v_payload,'{assignments}',v_expected,true);
        if v_sched.current_json ? 'targets' then
            v_payload=jsonb_set(v_payload,'{targets}',v_sched.current_json->'targets',true);
        end if;
        if v_sched.current_json ? 'request_snapshot' then
            v_payload=jsonb_set(v_payload,'{request_snapshot}',v_sched.current_json->'request_snapshot',true);
        end if;

        update public.schedules
           set current_json=v_payload,updated_at=now()
         where year=r.year and month=r.month;

        -- Rebuild the planned backup rows atomically with the ACTUAL rollback.
        for v_item in select value from jsonb_array_elements(p_backups)
        loop
            if nullif(v_item->>'covered_slot','') is null
               or nullif(v_item->>'planned_backup','') is null then
                raise exception 'INVALID_BACKUP_PLAN_ROW';
            end if;
            insert into public.backup_assignments(
                year,month,covered_slot,covered_person,covered_block,
                planned_backup,updated_at
            ) values (
                r.year,r.month,(v_item->>'covered_slot')::integer,
                nullif(v_item->>'covered_person',''),nullif(v_item->>'block',''),
                v_item->>'planned_backup',now()
            )
            on conflict (year,month,covered_slot)
            do update set
                covered_person=excluded.covered_person,
                covered_block=excluded.covered_block,
                planned_backup=excluded.planned_backup,
                updated_at=now();
        end loop;

        delete from public.backup_assignments b
         where b.year=r.year and b.month=r.month
           and b.completed_at is null
           and not exists (
               select 1 from jsonb_array_elements(p_backups) j
                where (j.value->>'covered_slot')::integer=b.covered_slot
           );
    end if;

    insert into public.schedule_action_deletions(
        year,month,action_type,original_table,original_id,
        original_payload,actual_undone,deleted_by
    ) values (
        r.year,r.month,
        case when v_kind='emergency_rescue' then 'emergency_rescue' else 'normal_swap' end,
        'swap_requests',r.id,to_jsonb(r),v_undo,auth.uid()
    );

    delete from public.swap_requests where id=r.id;

    return jsonb_build_object(
        'ok',true,'deleted',true,'undone_actual',v_undo,
        'action_type',case when v_kind='emergency_rescue' then 'emergency_rescue' else 'normal_swap' end,
        'request_id',r.id
    );
end;
$$;

revoke all on function public.delete_swap_action_v2586(bigint,jsonb,jsonb) from public;
grant execute on function public.delete_swap_action_v2586(bigint,jsonb,jsonb) to authenticated;


create or replace function public.delete_backup_swap_v2586(p_request_id bigint)
returns jsonb
language plpgsql
security definer
set search_path=public
as $$
declare
    r public.backup_swap_requests%rowtype;
    v_caller_initials text;
    a public.backup_assignments%rowtype;
    b public.backup_assignments%rowtype;
    v_undo boolean := false;
begin
    select up.initials into v_caller_initials
      from public.user_profiles up
     where up.user_id=auth.uid() and up.approved=true
     limit 1;

    select * into r from public.backup_swap_requests
     where id=p_request_id for update;
    if not found then raise exception 'BACKUP_SWAP_NOT_FOUND'; end if;

    if v_caller_initials is null and not public.is_senior(auth.uid()) then
        raise exception 'APPROVED_USER_REQUIRED';
    end if;
    if v_caller_initials is distinct from r.requester
       and v_caller_initials is distinct from r.target
       and not public.is_senior(auth.uid()) then
        raise exception 'DELETE_BACKUP_SWAP_NOT_AUTHORIZED';
    end if;

    if r.status='accepted' then
        select * into a from public.backup_assignments
         where year=r.year and month=r.month and covered_slot=r.requester_slot for update;
        if not found then raise exception 'UNDO_BACKUP_REQUESTER_SLOT_MISSING'; end if;
        select * into b from public.backup_assignments
         where year=r.year and month=r.month and covered_slot=r.target_slot for update;
        if not found then raise exception 'UNDO_BACKUP_TARGET_SLOT_MISSING'; end if;

        -- Do not overwrite later activation/manual override/completion.
        if a.activated_at is not null or b.activated_at is not null
           or a.completed_at is not null or b.completed_at is not null
           or a.actual_backup is not null or b.actual_backup is not null then
            raise exception 'UNDO_BACKUP_STALE: backup was activated/completed/overridden after the swap';
        end if;
        if a.planned_backup is distinct from r.target
           or b.planned_backup is distinct from r.requester then
            raise exception 'UNDO_BACKUP_STALE: backup holders changed again after the swap';
        end if;

        update public.backup_assignments
           set planned_backup=r.requester,updated_at=now()
         where id=a.id;
        update public.backup_assignments
           set planned_backup=r.target,updated_at=now()
         where id=b.id;
        v_undo=true;
    end if;

    insert into public.schedule_action_deletions(
        year,month,action_type,original_table,original_id,
        original_payload,actual_undone,deleted_by
    ) values (
        r.year,r.month,'backup_swap','backup_swap_requests',r.id,
        to_jsonb(r),v_undo,auth.uid()
    );

    delete from public.backup_swap_requests where id=r.id;

    return jsonb_build_object(
        'ok',true,'deleted',true,'undone_actual',v_undo,
        'action_type','backup_swap','request_id',r.id
    );
end;
$$;

revoke all on function public.delete_backup_swap_v2586(bigint) from public;
grant execute on function public.delete_backup_swap_v2586(bigint) to authenticated;
