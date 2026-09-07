-- V2.5.133 — Dream Team redagavimas SP ir ŠR
-- Leidžia tik patvirtintoms SP ir ŠR paskyroms skaityti bei keisti Dream Team nustatymus.

alter table public.sp_dream_team_config_v25125 enable row level security;
alter table public.sp_dream_team_monthly_v25125 enable row level security;

drop policy if exists "sp dream config select" on public.sp_dream_team_config_v25125;
drop policy if exists "sp dream config write" on public.sp_dream_team_config_v25125;
create policy "sp sr dream config select" on public.sp_dream_team_config_v25125
for select to authenticated using (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
);
create policy "sp sr dream config write" on public.sp_dream_team_config_v25125
for all to authenticated using (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
) with check (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
);

drop policy if exists "sp dream monthly select" on public.sp_dream_team_monthly_v25125;
drop policy if exists "sp dream monthly write" on public.sp_dream_team_monthly_v25125;
create policy "sp sr dream monthly select" on public.sp_dream_team_monthly_v25125
for select to authenticated using (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
);
create policy "sp sr dream monthly write" on public.sp_dream_team_monthly_v25125
for all to authenticated using (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
) with check (
  exists(
    select 1 from public.user_profiles up
    where up.user_id=(select auth.uid())
      and up.approved=true
      and up.initials in ('SP','ŠR')
  )
);

grant select,insert,update on public.sp_dream_team_config_v25125 to authenticated;
grant select,insert,update on public.sp_dream_team_monthly_v25125 to authenticated;
