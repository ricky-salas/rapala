-- Post-V2.5.90 authorization alignment.
-- R.Š. remains role='resident' and target_adjustment=0 for workload/account UI,
-- but retains the embedded senior/admin capabilities promised by the single-window design.
create or replace function public.is_senior(uid uuid)
returns boolean
language sql
stable
security definer
set search_path=public
as $$
  select exists (
    select 1
    from public.user_profiles p
    join public.resident_directory r on r.initials=p.initials
    where p.user_id=uid and p.approved=true
      and (r.role='senior' or p.initials='R.Š.')
  );
$$;
