
-- V2.5.89 AUTH IDENTITY LOCK
-- 1) Dedicated identity lookup: auth.uid() is the only source of resident identity.
-- 2) Harden claim flow: an already-linked auth user cannot rebind to another resident.
-- Existing schema already enforces:
--   PRIMARY KEY(user_id)
--   UNIQUE(initials)

create or replace function public.current_identity_v2589()
returns table(
  user_id uuid,
  initials text,
  email text,
  approved boolean,
  preferred_language text,
  access_role text
)
language sql
stable
security definer
set search_path = public, auth
as $$
  select
    up.user_id,
    up.initials,
    up.email,
    up.approved,
    up.preferred_language,
    up.access_role
  from public.user_profiles up
  where up.user_id = auth.uid()
  limit 1;
$$;

revoke all on function public.current_identity_v2589() from public;
grant execute on function public.current_identity_v2589() to authenticated;


create or replace function public.claim_resident_profile(
  p_initials text,
  p_invite_code text
)
returns table(initials text, full_name text, role text)
language plpgsql
security definer
set search_path = public, auth, extensions
as $$
declare
  v_user uuid := auth.uid();
  v_email text;
  v_invite public.resident_invites%rowtype;
  v_resident public.resident_directory%rowtype;
  v_existing public.user_profiles%rowtype;
begin
  if v_user is null then
    raise exception 'Authentication required';
  end if;

  -- Once one auth account is linked, its resident identity is immutable.
  select *
    into v_existing
  from public.user_profiles up
  where up.user_id = v_user;

  if found then
    if v_existing.access_role <> 'resident' then
      raise exception 'Account already linked to another access role';
    end if;

    if v_existing.initials is distinct from p_initials then
      raise exception 'ACCOUNT_ALREADY_BOUND_TO_%', coalesce(v_existing.initials,'UNKNOWN');
    end if;

    -- Idempotent re-submit for the SAME resident only.
    select *
      into v_resident
    from public.resident_directory rd
    where rd.initials = v_existing.initials;

    return query
      select v_resident.initials, v_resident.full_name, v_resident.role;
    return;
  end if;

  select email
    into v_email
  from auth.users
  where id = v_user;

  select *
    into v_invite
  from public.resident_invites ri
  where ri.initials = p_initials
  for update;

  if not found then
    raise exception 'Invalid invite';
  end if;

  if v_invite.used_by is not null and v_invite.used_by <> v_user then
    raise exception 'Invite already used';
  end if;

  if crypt(p_invite_code, v_invite.invite_hash) <> v_invite.invite_hash then
    raise exception 'Invalid invite';
  end if;

  if exists(
    select 1
    from public.user_profiles up
    where up.initials = p_initials
      and up.user_id <> v_user
  ) then
    raise exception 'Resident already claimed';
  end if;

  insert into public.user_profiles(
    user_id, initials, email, approved, access_role, updated_at
  )
  values(
    v_user, p_initials, coalesce(v_email,''), true, 'resident', now()
  );

  update public.account_settings
  set email = coalesce(v_email,email),
      updated_at = now()
  where account_settings.initials = p_initials;

  update public.resident_invites
  set used_by = v_user,
      used_at = now()
  where resident_invites.initials = p_initials;

  select *
    into v_resident
  from public.resident_directory rd
  where rd.initials = p_initials;

  return query
    select v_resident.initials, v_resident.full_name, v_resident.role;
end;
$$;

revoke all on function public.claim_resident_profile(text,text) from public;
grant execute on function public.claim_resident_profile(text,text) to authenticated;
