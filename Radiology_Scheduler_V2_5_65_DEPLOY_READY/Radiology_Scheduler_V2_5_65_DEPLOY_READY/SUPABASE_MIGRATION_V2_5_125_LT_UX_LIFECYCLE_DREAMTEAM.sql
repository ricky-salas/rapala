-- V2.5.125 — LIETUVIŠKA UX + 14/15/16 CIKLAS + SP DREAM TEAM
--
-- Mėnesio eiga pagal Europe/Vilnius laiką:
--   1 d. 00:00 -> 14 d. 00:00   rezidentų pageidavimai
--   14 d. 00:00 -> 15 d. 00:00  seniūnė generuoja, tikrina ir paskelbia preliminarų grafiką
--   15 d. 00:00 -> 16 d. 00:00  24 val. rezidentų apsikeitimų langas
--   nuo 16 d. 00:00             rezidentų savitarna užrakinta; seniūnė atlieka rankinę patikrą ir tvirtina galutinį grafiką
--
-- Pateikimo vieta 1–16 taikoma TAM PAČIAM grafikui. DB laukas points_awarded paliekamas
-- tik atgaliniam suderinamumui; vartotojo sąsajoje taškai neberodomi.

create or replace function public.swap_window_open_v25125(p_year integer,p_month integer)
returns timestamptz
language plpgsql immutable
set search_path to 'public'
as $$
declare py integer; pm integer;
begin
  if p_month=1 then py:=p_year-1; pm:=12; else py:=p_year; pm:=p_month-1; end if;
  return (make_date(py,pm,15)::timestamp at time zone 'Europe/Vilnius');
end;
$$;
grant execute on function public.swap_window_open_v25125(integer,integer) to authenticated;

create or replace function public.scheduler_cycle_phase_v25119(p_year integer,p_month integer)
returns jsonb
language plpgsql stable
set search_path to 'public'
as $$
declare
  v_open timestamptz:=public.preference_window_open_v25118(p_year,p_month);
  v_pref_close timestamptz:=public.preference_cutoff_v2595(p_year,p_month);
  v_swap_open timestamptz:=public.swap_window_open_v25125(p_year,p_month);
  v_swap_close timestamptz:=public.swap_window_close_v25119(p_year,p_month);
  v_phase text;
begin
  v_phase:=case
    when now()<v_open then 'not_open'
    when now()<v_pref_close then 'preferences'
    when now()<v_swap_open then 'senior_build'
    when now()<v_swap_close then 'swaps'
    else 'senior_review'
  end;
  return jsonb_build_object(
    'phase',v_phase,
    'preference_open',v_open,
    'preference_close',v_pref_close,
    'preliminary_deadline',v_swap_open,
    'swap_open',v_swap_open,
    'swap_close',v_swap_close,
    'server_now',now()
  );
end;
$$;
grant execute on function public.scheduler_cycle_phase_v25119(integer,integer) to authenticated;

-- Rezidentų nauji apsikeitimai leidžiami tik 15 d. 00:00–16 d. 00:00.
create or replace function public._swap_submission_allowed_v2591(p_year integer,p_month integer,p_initials text)
returns boolean
language plpgsql security definer
set search_path to 'public','auth'
as $$
declare v_state text; v_deadline timestamptz; v_start timestamptz; v_close timestamptz;
begin
  if (p_year*100+p_month)>=202610 then
    v_start:=public.swap_window_open_v25125(p_year,p_month);
    v_close:=public.swap_window_close_v25119(p_year,p_month);
    if now()<v_start or now()>=v_close then return false; end if;
    if exists(select 1 from public.schedule_lifecycle where year=p_year and month=p_month and state='final') then return false; end if;
    return exists(
      select 1 from public.schedules s
      where s.year=p_year and s.month=p_month and s.status='published'
        and s.baseline_json is not null and s.current_json is not null
    );
  end if;
  select state,swap_deadline into v_state,v_deadline
  from public.schedule_lifecycle where year=p_year and month=p_month for update;
  if v_state is null or v_state='final' then return false; end if;
  if v_state='swap_open' and v_deadline is not null and now()<=v_deadline then return true; end if;
  return public._consume_late_swap_access_v2591(p_year,p_month,p_initials);
end;
$$;

-- Saugomas lifecycle įrašas sinchronizuojamas su nauju 15–16 d. apsikeitimų langu.
create or replace function public.sync_schedule_cycle_v25119(p_year integer,p_month integer)
returns jsonb
language plpgsql security definer
set search_path to 'public'
as $$
declare
  v_swap_open timestamptz:=public.swap_window_open_v25125(p_year,p_month);
  v_swap_close timestamptz:=public.swap_window_close_v25119(p_year,p_month);
  v_phase jsonb; v_has_published boolean;
begin
  v_phase:=public.scheduler_cycle_phase_v25119(p_year,p_month);
  if (p_year*100+p_month)<202610 then return v_phase; end if;
  select exists(
    select 1 from public.schedules s
    where s.year=p_year and s.month=p_month and s.status='published' and s.current_json is not null
  ) into v_has_published;

  if now()>=v_swap_open and now()<v_swap_close and v_has_published then
    insert into public.schedule_lifecycle(year,month,state,swap_opened_at,swap_deadline,updated_at)
    values(p_year,p_month,'swap_open',v_swap_open,v_swap_close,now())
    on conflict(year,month) do update set
      state=case when public.schedule_lifecycle.state='final' then 'final' else 'swap_open' end,
      swap_opened_at=coalesce(public.schedule_lifecycle.swap_opened_at,v_swap_open),
      swap_deadline=v_swap_close,swap_closed_at=null,updated_at=now();
  elsif now()>=v_swap_close then
    perform public.auto_fill_weekend_backups_v25119(p_year,p_month);
    insert into public.schedule_lifecycle(year,month,state,swap_deadline,swap_closed_at,updated_at)
    values(p_year,p_month,'swap_closed',v_swap_close,v_swap_close,now())
    on conflict(year,month) do update set
      state=case when public.schedule_lifecycle.state='final' then 'final' else 'swap_closed' end,
      swap_deadline=v_swap_close,
      swap_closed_at=coalesce(public.schedule_lifecycle.swap_closed_at,v_swap_close),
      updated_at=now();
  end if;
  return public.scheduler_cycle_phase_v25119(p_year,p_month);
end;
$$;
grant execute on function public.sync_schedule_cycle_v25119(integer,integer) to authenticated;

-- ---------------------------------------------------------------------------
-- SP privatus Dream Team konfigūravimas
-- ---------------------------------------------------------------------------
create table if not exists public.sp_dream_team_config_v25125(
  id integer primary key default 1 check(id=1),
  centro_members text[] not null default array['SP','ŠR','GE']::text[],
  adc_members text[] not null default array['SP','ŠR']::text[],
  updated_at timestamptz not null default now(),
  check(cardinality(centro_members) between 2 and 4),
  check(cardinality(adc_members)=2)
);

insert into public.sp_dream_team_config_v25125(id,centro_members,adc_members)
values(1,array['SP','ŠR','GE']::text[],array['SP','ŠR']::text[])
on conflict(id) do nothing;

create table if not exists public.sp_dream_team_monthly_v25125(
  year integer not null,
  month integer not null check(month between 1 and 12),
  centro_target integer not null default 4 check(centro_target between 0 and 6),
  adc_target integer not null default 0 check(adc_target between 0 and 12),
  updated_at timestamptz not null default now(),
  primary key(year,month)
);

alter table public.sp_dream_team_config_v25125 enable row level security;
alter table public.sp_dream_team_monthly_v25125 enable row level security;

drop policy if exists "sp dream config select" on public.sp_dream_team_config_v25125;
create policy "sp dream config select" on public.sp_dream_team_config_v25125
for select to authenticated using (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
);
drop policy if exists "sp dream config write" on public.sp_dream_team_config_v25125;
create policy "sp dream config write" on public.sp_dream_team_config_v25125
for all to authenticated using (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
) with check (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
);

drop policy if exists "sp dream monthly select" on public.sp_dream_team_monthly_v25125;
create policy "sp dream monthly select" on public.sp_dream_team_monthly_v25125
for select to authenticated using (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
);
drop policy if exists "sp dream monthly write" on public.sp_dream_team_monthly_v25125;
create policy "sp dream monthly write" on public.sp_dream_team_monthly_v25125
for all to authenticated using (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
) with check (
  exists(select 1 from public.user_profiles up where up.user_id=(select auth.uid()) and up.approved=true and up.initials='SP')
);

grant select,insert,update on public.sp_dream_team_config_v25125 to authenticated;
grant select,insert,update on public.sp_dream_team_monthly_v25125 to authenticated;

-- Kiti lifecycle operatoriai gali sužinoti tik ar šį mėnesį yra aktyvus privatus
-- Dream Team tikslas, bet ne komandos sudėtį.
create or replace function public.sp_dream_team_active_v25125(p_year integer,p_month integer)
returns boolean
language plpgsql stable security definer
set search_path to 'public','auth'
as $$
declare v_c integer:=4; v_a integer:=0;
begin
  if not public.is_lifecycle_operator_v2592(auth.uid()) then return false; end if;
  select centro_target,adc_target into v_c,v_a
  from public.sp_dream_team_monthly_v25125
  where year=p_year and month=p_month;
  if not found then
    v_c:=4; v_a:=0;
  end if;
  return coalesce(v_c,0)>0 or coalesce(v_a,0)>0;
end;
$$;
grant execute on function public.sp_dream_team_active_v25125(integer,integer) to authenticated;

-- Spalio ciklui, jei mėnesio eilutės dar nėra, išsaugome suderinamą ankstesnio
-- CENTRO RO tikslo numatytąją reikšmę. SP vėliau gali ją keisti UI.
insert into public.sp_dream_team_monthly_v25125(year,month,centro_target,adc_target)
values(2026,10,4,0)
on conflict(year,month) do nothing;
