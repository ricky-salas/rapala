-- V2.5.148 — SWAP + vienpusio pamainos atidavimo registras
-- Šis registras yra auditinis sluoksnis. Jis pats nekeičia ACTUAL grafiko.
-- SP ir ŠR mato visus įrašus; rezidentas mato tik savo donor/gavėjo įrašus.

create table if not exists public.shift_giveaway_registry_v25148 (
  id bigserial primary key,
  year integer not null,
  month integer not null check (month between 1 and 12),
  donor_initials text not null,
  slot_id integer not null,
  record_type text not null check (record_type in ('offer','handed_off')),
  recipient_initials text null,
  note text not null default '',
  status text not null default 'active' check (status in ('active','cancelled')),
  registered_at timestamptz not null default now(),
  cancelled_at timestamptz null,
  created_by uuid not null default auth.uid(),
  constraint shift_giveaway_recipient_guard check (
    (record_type='offer' and recipient_initials is null)
    or
    (record_type='handed_off' and recipient_initials is not null and recipient_initials<>donor_initials)
  )
);

create index if not exists shift_giveaway_month_idx_v25148
  on public.shift_giveaway_registry_v25148(year,month,registered_at desc);
create index if not exists shift_giveaway_people_idx_v25148
  on public.shift_giveaway_registry_v25148(donor_initials,recipient_initials);

alter table public.shift_giveaway_registry_v25148 enable row level security;

drop policy if exists shift_giveaway_read_v25148 on public.shift_giveaway_registry_v25148;
create policy shift_giveaway_read_v25148
on public.shift_giveaway_registry_v25148
for select to authenticated
using (
  exists (
    select 1
    from public.user_profiles up
    where up.user_id=auth.uid()
      and up.approved=true
      and (
        up.initials in ('SP','ŠR')
        or up.initials=donor_initials
        or up.initials=recipient_initials
      )
  )
);

grant select on public.shift_giveaway_registry_v25148 to authenticated;
revoke insert,update,delete on public.shift_giveaway_registry_v25148 from authenticated;

create or replace function public.create_shift_giveaway_record_v25148(
  p_year integer,
  p_month integer,
  p_slot_id integer,
  p_record_type text,
  p_recipient_initials text default null,
  p_note text default ''
)
returns public.shift_giveaway_registry_v25148
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_uid uuid:=auth.uid();
  v_initials text;
  v_current jsonb;
  v_owner text;
  v_row public.shift_giveaway_registry_v25148%rowtype;
begin
  if v_uid is null then raise exception 'AUTH_REQUIRED'; end if;
  select up.initials into v_initials
  from public.user_profiles up
  where up.user_id=v_uid and up.approved=true
  limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;

  if p_record_type not in ('offer','handed_off') then
    raise exception 'GIVEAWAY_RECORD_TYPE_INVALID';
  end if;
  if p_record_type='offer' then
    p_recipient_initials:=null;
  else
    if p_recipient_initials is null or p_recipient_initials=v_initials then
      raise exception 'GIVEAWAY_RECIPIENT_INVALID';
    end if;
    if not exists(
      select 1 from public.resident_directory rd
      where rd.initials=p_recipient_initials and coalesce(rd.active,true)=true
    ) then raise exception 'GIVEAWAY_RECIPIENT_UNKNOWN'; end if;
  end if;

  select s.current_json into v_current
  from public.schedules s
  where s.year=p_year and s.month=p_month and s.status='published' and s.current_json is not null
  limit 1;
  if v_current is null then raise exception 'GIVEAWAY_ONLY_AFTER_PUBLICATION'; end if;

  v_owner:=v_current->'assignments'->>(p_slot_id::text);
  if v_owner is distinct from v_initials then
    raise exception 'GIVEAWAY_SLOT_NOT_OWNED_BY_CURRENT_USER';
  end if;

  if exists(
    select 1 from public.shift_giveaway_registry_v25148 g
    where g.year=p_year and g.month=p_month and g.slot_id=p_slot_id
      and g.donor_initials=v_initials and g.status='active'
  ) then raise exception 'GIVEAWAY_ACTIVE_RECORD_ALREADY_EXISTS'; end if;

  insert into public.shift_giveaway_registry_v25148(
    year,month,donor_initials,slot_id,record_type,recipient_initials,note,status,registered_at,created_by
  ) values (
    p_year,p_month,v_initials,p_slot_id,p_record_type,p_recipient_initials,coalesce(trim(p_note),''),'active',now(),v_uid
  ) returning * into v_row;
  return v_row;
end;
$$;
grant execute on function public.create_shift_giveaway_record_v25148(integer,integer,integer,text,text,text) to authenticated;

create or replace function public.cancel_shift_giveaway_record_v25148(p_id bigint)
returns public.shift_giveaway_registry_v25148
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare
  v_initials text;
  v_row public.shift_giveaway_registry_v25148%rowtype;
begin
  select up.initials into v_initials
  from public.user_profiles up
  where up.user_id=auth.uid() and up.approved=true
  limit 1;
  if v_initials is null then raise exception 'APPROVED_PROFILE_REQUIRED'; end if;

  select * into v_row
  from public.shift_giveaway_registry_v25148
  where id=p_id
  for update;
  if not found then raise exception 'GIVEAWAY_RECORD_NOT_FOUND'; end if;
  if v_initials not in ('SP','ŠR') and v_initials<>v_row.donor_initials then
    raise exception 'GIVEAWAY_CANCEL_NOT_ALLOWED';
  end if;

  update public.shift_giveaway_registry_v25148
  set status='cancelled',cancelled_at=now()
  where id=p_id
  returning * into v_row;
  return v_row;
end;
$$;
grant execute on function public.cancel_shift_giveaway_record_v25148(bigint) to authenticated;
