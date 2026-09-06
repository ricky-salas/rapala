-- V2.5.113 — canonical roster initials correction
-- Corrects only two identifiers while preserving linked accounts and all history:
--   SK -> SŠ (Stašinskas Kipras)
--   SR -> SP (Steponavičiūtė Rosita; operational senior)

create temp table if not exists _v25113_initials_map (
  old_initials text primary key,
  new_initials text not null unique,
  full_name text not null
) on commit drop;

truncate _v25113_initials_map;
insert into _v25113_initials_map(old_initials,new_initials,full_name) values
('SK','SŠ','Stašinskas Kipras'),
('SR','SP','Steponavičiūtė Rosita');

-- The WESTON table had an exact SR-only CHECK. Temporarily remove it so the
-- identity row can be migrated atomically, then restore it for SP.
do $$
begin
  if exists (
    select 1 from pg_constraint
    where conrelid='public.weston_beer_ledger_v25110'::regclass
      and conname='weston_beer_ledger_v25110_initials_check'
  ) then
    alter table public.weston_beer_ledger_v25110
      drop constraint weston_beer_ledger_v25110_initials_check;
  end if;
end $$;

-- Create corrected parent keys first. This lets all non-cascading child foreign
-- keys move safely without recreating accounts or losing settings/history.
insert into public.resident_directory(initials,full_name,role,target_adjustment,color,active)
select m.new_initials,m.full_name,r.role,r.target_adjustment,r.color,r.active
from public.resident_directory r
join _v25113_initials_map m on m.old_initials=r.initials
on conflict(initials) do update set
  full_name=excluded.full_name,
  role=excluded.role,
  target_adjustment=excluded.target_adjustment,
  color=excluded.color,
  active=excluded.active;

-- Normalize the corrected parent rows if this migration is inspected/replayed.
update public.resident_directory r
set full_name=m.full_name
from _v25113_initials_map m
where r.initials=m.new_initials;

-- Rewrite exact roster tokens in every ordinary public text column. This covers
-- user_profiles, preferences, account settings, swaps, backups, audit rows,
-- credits, invitations, fairness history and any future identity text columns.
do $$
declare rec record;
begin
  for rec in
    select col.table_schema,col.table_name,col.column_name
    from information_schema.columns col
    join information_schema.tables tbl
      on tbl.table_schema=col.table_schema
     and tbl.table_name=col.table_name
     and tbl.table_type='BASE TABLE'
    where col.table_schema='public'
      and col.data_type in ('text','character varying','character')
      and col.is_generated='NEVER'
      and not (col.table_name='resident_directory' and col.column_name='initials')
  loop
    execute format(
      'update %I.%I t set %I=m.new_initials from _v25113_initials_map m where t.%I=m.old_initials',
      rec.table_schema,rec.table_name,rec.column_name,rec.column_name
    );
  end loop;
end $$;

-- Rewrite exact JSON string values and JSON object keys. Free-text substrings are
-- intentionally not changed.
do $$
declare rec record; m record; expr text;
begin
  for rec in
    select col.table_schema,col.table_name,col.column_name
    from information_schema.columns col
    join information_schema.tables tbl
      on tbl.table_schema=col.table_schema
     and tbl.table_name=col.table_name
     and tbl.table_type='BASE TABLE'
    where col.table_schema='public' and col.data_type='jsonb'
  loop
    expr := format('%I::text',rec.column_name);
    for m in select * from _v25113_initials_map order by old_initials loop
      expr := format('replace(%s,%L,%L)',expr,'"'||m.old_initials||'"','"'||m.new_initials||'"');
    end loop;
    execute format(
      'update %I.%I set %I=(%s)::jsonb where %I is not null',
      rec.table_schema,rec.table_name,rec.column_name,expr,rec.column_name
    );
  end loop;
end $$;

-- Remove obsolete parent keys only after all children moved.
delete from public.resident_directory r
using _v25113_initials_map m
where r.initials=m.old_initials;

-- Restore the WESTON identity guard for the corrected operational leader.
alter table public.weston_beer_ledger_v25110
  add constraint weston_beer_ledger_v25110_initials_check
  check (initials='SP');

-- Existing RPC names are intentionally preserved for API compatibility, but any
-- exact hard-coded roster literal inside their definitions is corrected. We only
-- replace quoted literals ('SR'/'SK'), never arbitrary substrings or function names.
do $$
declare f record; def text;
begin
  for f in
    select p.oid
    from pg_proc p
    join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public'
      and p.prokind in ('f','p')
      and (
        pg_get_functiondef(p.oid) like '%''SR''%'
        or pg_get_functiondef(p.oid) like '%''SK''%'
      )
  loop
    def:=pg_get_functiondef(f.oid);
    def:=replace(def,'''SR''','''SP''');
    def:=replace(def,'''SK''','''SŠ''');
    execute def;
  end loop;
end $$;

-- Final integrity assertions.
do $$
declare n integer; v_role text; v_adj integer;
begin
  select count(*) into n from public.resident_directory where active=true;
  if n<>16 then
    raise exception 'V2.5.113 expected 16 active residents, found %',n;
  end if;

  select count(*) into n from public.resident_directory where initials in ('SR','SK');
  if n<>0 then
    raise exception 'V2.5.113 old initials remain in resident_directory: % rows',n;
  end if;

  select count(*) into n from public.resident_directory where initials in ('SP','SŠ');
  if n<>2 then
    raise exception 'V2.5.113 corrected initials missing: expected SP and SŠ';
  end if;

  select role,target_adjustment into v_role,v_adj
  from public.resident_directory where initials='SP';
  if v_role is distinct from 'senior' or v_adj is distinct from -2 then
    raise exception 'V2.5.113 SP must remain senior with target_adjustment=-2';
  end if;
end $$;
