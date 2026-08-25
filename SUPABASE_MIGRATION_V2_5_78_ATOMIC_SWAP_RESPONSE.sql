-- V2.5.78 atomic normal-swap response.
-- Applied to production project during build.

create or replace function public.respond_swap_request_v2578(
    p_request_id bigint,
    p_action text,
    p_reason text default null
)
returns public.swap_requests
language plpgsql
security definer
set search_path=public
as $$
declare
    r public.swap_requests%rowtype;
    caller_initials text;
    v_action text:=lower(trim(coalesce(p_action,'')));
begin
    select initials into caller_initials
    from public.user_profiles
    where user_id=auth.uid() and approved=true
    limit 1;

    if caller_initials is null and not public.is_senior(auth.uid()) then
        raise exception 'APPROVED_USER_REQUIRED';
    end if;

    select * into r
    from public.swap_requests
    where id=p_request_id
    for update;

    if not found then raise exception 'SWAP_REQUEST_NOT_FOUND'; end if;
    if r.status <> 'pending' then
        raise exception 'SWAP_REQUEST_ALREADY_RESPONDED:%',r.status;
    end if;

    if v_action='accept' then
        if caller_initials is distinct from r.person_b and not public.is_senior(auth.uid()) then
            raise exception 'SWAP_ACCEPT_NOT_AUTHORIZED';
        end if;
        update public.swap_requests
        set status='approved', reason=coalesce(p_reason,reason), responded_at=now()
        where id=r.id returning * into r;

    elsif v_action='reject' then
        if caller_initials is distinct from r.person_b and not public.is_senior(auth.uid()) then
            raise exception 'SWAP_REJECT_NOT_AUTHORIZED';
        end if;
        update public.swap_requests
        set status='rejected',
            reason=coalesce(nullif(p_reason,''),'declined'),
            responded_at=now()
        where id=r.id returning * into r;

    elsif v_action='cancel' then
        if caller_initials is distinct from r.person_a and not public.is_senior(auth.uid()) then
            raise exception 'SWAP_CANCEL_NOT_AUTHORIZED';
        end if;
        update public.swap_requests
        set status='rejected',
            reason=coalesce(nullif(p_reason,''),'cancelled_by_requester'),
            responded_at=now()
        where id=r.id returning * into r;
    else
        raise exception 'INVALID_SWAP_ACTION';
    end if;

    return r;
end;
$$;

revoke all on function public.respond_swap_request_v2578(bigint,text,text) from public;
grant execute on function public.respond_swap_request_v2578(bigint,text,text) to authenticated;
revoke execute on function public.cancel_swap_request(bigint) from anon;
revoke execute on function public.cancel_backup_swap_request(bigint) from anon;
