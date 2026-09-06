-- V2.5.118B — exact 16-slot FCFS weekend catalog guard
alter table public.weekend_backup_claims
  add column if not exists claim_day integer,
  add column if not exists claim_block text;

create unique index if not exists weekend_backup_claims_month_day_block_v25118_uidx
on public.weekend_backup_claims(year,month,claim_day,claim_block)
where claim_day is not null and claim_block is not null;

create or replace function public.is_fcfs_weekend_backup_slot_v25118(
  p_year integer,p_month integer,p_day integer,p_block text
)
returns boolean
language sql
immutable
set search_path to 'public'
as $$
  with weekend_days as (
    select d::date as dt,
           extract(day from d)::integer as day_no,
           extract(isodow from d)::integer as iso_dow,
           case
             when extract(isodow from d)=6
               and extract(month from d+interval '1 day')=p_month then 0
             when extract(isodow from d)=7
               and extract(month from d-interval '1 day')=p_month then 0
             else 1
           end as orphan_rank
    from generate_series(
      make_date(p_year,p_month,1)::timestamp,
      (date_trunc('month',make_date(p_year,p_month,1))+interval '1 month - 1 day')::timestamp,
      interval '1 day'
    ) d
    where extract(isodow from d) in (6,7)
  ), selected_days as (
    select day_no
    from weekend_days
    order by orphan_rank, day_no
    limit 8
  )
  select p_block in ('AM','PM') and exists(select 1 from selected_days where day_no=p_day);
$$;

grant execute on function public.is_fcfs_weekend_backup_slot_v25118(integer,integer,integer,text) to authenticated;

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
  if not public.is_fcfs_weekend_backup_slot_v25118(p_year,p_month,p_day,p_block)
    then raise exception 'BACKUP_SLOT_OUTSIDE_16_SLOT_CATALOG'; end if;

  perform pg_advisory_xact_lock(25119, p_year*100+p_month);

  select * into v_existing from public.weekend_backup_claims
  where year=p_year and month=p_month and initials=v_initials for update;
  if found and v_existing.covered_slot=p_covered_slot
     and v_existing.claim_day=p_day and v_existing.claim_block=p_block then
    return v_existing;
  end if;

  select * into v_owner from public.weekend_backup_claims
  where year=p_year and month=p_month
    and (covered_slot=p_covered_slot or (claim_day=p_day and claim_block=p_block))
  for update limit 1;
  if found and v_owner.initials is distinct from v_initials then
    raise exception 'BACKUP_SLOT_ALREADY_CLAIMED';
  end if;

  select count(*)::integer into v_count
  from public.weekend_backup_claims
  where year=p_year and month=p_month and initials<>v_initials;
  if v_count>=16 then raise exception 'BACKUP_FCFS_FULL'; end if;

  delete from public.weekend_backup_claims
  where year=p_year and month=p_month and initials=v_initials;

  insert into public.weekend_backup_claims(
    year,month,covered_slot,initials,source,claimed_at,updated_at,claim_day,claim_block
  ) values(
    p_year,p_month,p_covered_slot,v_initials,'self_fcfs',now(),now(),p_day,p_block
  ) returning * into v_row;
  return v_row;
end;
$$;

grant execute on function public.claim_weekend_backup_fcfs_v25118(integer,integer,integer,integer,text) to authenticated;
