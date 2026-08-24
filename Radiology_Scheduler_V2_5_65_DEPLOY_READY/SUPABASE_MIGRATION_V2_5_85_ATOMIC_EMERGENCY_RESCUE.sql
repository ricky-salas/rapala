-- V2.5.85 — Atomic Emergency Rescue
-- Applies ACTUAL assignment transfer, backup-plan synchronization and audit row
-- in one SECURITY DEFINER transaction. Resident may only apply a rescue where
-- they are the mover (or a senior may apply it).

create or replace function public.apply_emergency_rescue_v2585(
    p_year integer,
    p_month integer,
    p_source_slot integer,
    p_target_slot integer,
    p_mover text,
    p_rescued_person text,
    p_current_json jsonb,
    p_backups jsonb,
    p_reason text default ''
)
returns jsonb
language plpgsql
security definer
set search_path=public
as $$
declare
    v_caller_initials text;
    v_sched public.schedules%rowtype;
    v_assign jsonb;
    v_expected_assign jsonb;
    v_payload jsonb;
    v_item jsonb;
    v_audit_id bigint;
    v_existing_id bigint;
begin
    select up.initials
      into v_caller_initials
      from public.user_profiles up
     where up.user_id=auth.uid()
       and up.approved=true
     limit 1;

    if v_caller_initials is null and not public.is_senior(auth.uid()) then
        raise exception 'APPROVED_USER_REQUIRED';
    end if;

    if v_caller_initials is distinct from p_mover and not public.is_senior(auth.uid()) then
        raise exception 'EMERGENCY_RESCUE_NOT_AUTHORIZED';
    end if;

    -- Idempotent network retry: if the exact same audit token already committed,
    -- return success instead of applying a second rescue.
    select sr.id
      into v_existing_id
      from public.swap_requests sr
     where sr.year=p_year
       and sr.month=p_month
       and sr.slot_a=p_source_slot
       and sr.slot_b=p_target_slot
       and sr.person_a=p_mover
       and sr.person_b=p_rescued_person
       and sr.status='approved'
       and sr.reason=coalesce(p_reason,'')
     order by sr.id desc
     limit 1;

    if v_existing_id is not null then
        return jsonb_build_object(
            'ok',true,
            'rescue_id',v_existing_id,
            'idempotent',true
        );
    end if;

    select *
      into v_sched
      from public.schedules s
     where s.year=p_year
       and s.month=p_month
       and s.status='published'
     for update;

    if not found or v_sched.current_json is null then
        raise exception 'PUBLISHED_CURRENT_NOT_FOUND';
    end if;

    if jsonb_typeof(coalesce(p_backups,'[]'::jsonb)) <> 'array' then
        raise exception 'BACKUP_PLAN_MUST_BE_JSON_ARRAY';
    end if;

    v_assign=coalesce(v_sched.current_json->'assignments','{}'::jsonb);

    if (v_assign->>p_source_slot::text) is distinct from p_mover then
        raise exception 'EMERGENCY_SOURCE_STALE: expected %, found %',
            p_mover, coalesce(v_assign->>p_source_slot::text,'EMPTY');
    end if;

    if (v_assign->>p_target_slot::text) is distinct from p_rescued_person then
        raise exception 'EMERGENCY_TARGET_STALE: expected %, found %',
            p_rescued_person, coalesce(v_assign->>p_target_slot::text,'EMPTY');
    end if;

    v_expected_assign=(v_assign - p_source_slot::text)
        || jsonb_build_object(p_target_slot::text,p_mover);

    if coalesce(p_current_json->'assignments','{}'::jsonb) is distinct from v_expected_assign then
        raise exception 'EMERGENCY_PAYLOAD_ASSIGNMENT_MISMATCH';
    end if;

    -- Client may provide refreshed operational stats, but immutable publication
    -- request/target ledgers are forced back to their existing stored values.
    v_payload=coalesce(p_current_json,'{}'::jsonb);
    v_payload=jsonb_set(v_payload,'{assignments}',v_expected_assign,true);

    if v_sched.current_json ? 'targets' then
        v_payload=jsonb_set(v_payload,'{targets}',v_sched.current_json->'targets',true);
    end if;
    if v_sched.current_json ? 'request_snapshot' then
        v_payload=jsonb_set(v_payload,'{request_snapshot}',v_sched.current_json->'request_snapshot',true);
    end if;

    update public.schedules
       set current_json=v_payload,
           updated_at=now()
     where year=p_year and month=p_month;

    -- Synchronize planned backup rows while preserving actual activation/completion
    -- fields from any existing rows.
    for v_item in
        select value from jsonb_array_elements(coalesce(p_backups,'[]'::jsonb))
    loop
        if nullif(v_item->>'covered_slot','') is null
           or nullif(v_item->>'planned_backup','') is null then
            raise exception 'INVALID_BACKUP_PLAN_ROW';
        end if;

        insert into public.backup_assignments(
            year,month,covered_slot,covered_person,covered_block,
            planned_backup,updated_at
        ) values (
            p_year,
            p_month,
            (v_item->>'covered_slot')::integer,
            nullif(v_item->>'covered_person',''),
            nullif(v_item->>'block',''),
            v_item->>'planned_backup',
            now()
        )
        on conflict (year,month,covered_slot)
        do update set
            covered_person=excluded.covered_person,
            covered_block=excluded.covered_block,
            planned_backup=excluded.planned_backup,
            updated_at=now();
    end loop;

    delete from public.backup_assignments b
     where b.year=p_year
       and b.month=p_month
       and b.completed_at is null
       and not exists (
           select 1
             from jsonb_array_elements(coalesce(p_backups,'[]'::jsonb)) j
            where (j.value->>'covered_slot')::integer=b.covered_slot
       );

    insert into public.swap_requests(
        year,month,slot_a,slot_b,person_a,person_b,
        status,reason,created_at,responded_at
    ) values (
        p_year,p_month,p_source_slot,p_target_slot,p_mover,p_rescued_person,
        'approved',coalesce(p_reason,''),now(),now()
    ) returning id into v_audit_id;

    return jsonb_build_object(
        'ok',true,
        'rescue_id',v_audit_id,
        'idempotent',false,
        'source_vacated',true,
        'target_person',p_mover,
        'rescued_person',p_rescued_person,
        'workload_credit_neutral',true
    );
end;
$$;

revoke all on function public.apply_emergency_rescue_v2585(
    integer,integer,integer,integer,text,text,jsonb,jsonb,text
) from public;

grant execute on function public.apply_emergency_rescue_v2585(
    integer,integer,integer,integer,text,text,jsonb,jsonb,text
) to authenticated;
