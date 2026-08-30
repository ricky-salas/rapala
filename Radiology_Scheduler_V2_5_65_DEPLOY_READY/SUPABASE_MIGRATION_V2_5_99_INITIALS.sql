-- V2.5.99 — roster initials migration
-- Preserves linked accounts, settings, preferences, schedules, swaps, backups,
-- audit/research history and resident colors/roles while changing roster identifiers.

create temp table if not exists _v2599_roster_map (
  old_initials text primary key,
  new_initials text not null unique,
  old_name text not null,
  new_name text not null
) on commit drop;

truncate _v2599_roster_map;
insert into _v2599_roster_map(old_initials,new_initials,old_name,new_name) values
('G.M.','MG','Gabrielė Maleckaitė','Maleckaitė Gabrielė'),
('A.S.','SA','Arminas Sveboda','Sveboda Arminas'),
('A.P.','PV','Aistė Pileckienė','Pileckienė Aistė'),
('K.S.','SK','Kipras Strašinskas','Stašinskas Kipras'),
('I.M.','MŽ','Ignas Mažonavičius','Mažonavičius Ignas'),
('E.K.','KE','Elena Khatskeleva','Khatskeleva Elena'),
('L.V.','VL','Laura Volkovskaja','Volkovskaja Laura'),
('J.G.','GB','Justinas Grumblys','Grumblys Justinas'),
('R.Š.','ŠR','Rapolas Šalaševičius','Šalaševičius Rapolas'),
('R.S.','SR','Rosita Steponavičiūtė','Steponavičiūtė Rosita'),
('E.S.','SE','Eglė Stanisauskytė','Stanišauskytė Eglė'),
('D.G.','GD','Deivydas Giedrimas','Giedrimas Deivydas'),
('R.M.','MR','Reda Montvilaitė','Montvilaitė Reda'),
('E.G.','GE','Ernestas Gertas','Gertas Ernestas'),
('V.S.','SN','Vytautė Stankevičiūtė','Stankevičiūtė Vytautė'),
('S.D.','DU','Sofija Dulkė','Dulkė Sofija Ana');

-- Create the new parent keys first so non-cascading foreign keys can be moved safely.
insert into public.resident_directory(initials,full_name,role,target_adjustment,color,active)
select m.new_initials,m.new_name,r.role,r.target_adjustment,r.color,r.active
from public.resident_directory r
join _v2599_roster_map m on m.old_initials=r.initials
on conflict(initials) do update set
  full_name=excluded.full_name,
  role=excluded.role,
  target_adjustment=excluded.target_adjustment,
  color=excluded.color,
  active=excluded.active;

-- Idempotent name normalization if the migration is inspected/replayed after keys already moved.
update public.resident_directory r
set full_name=m.new_name
from _v2599_roster_map m
where r.initials=m.new_initials;

-- Update every ordinary text/varchar column whose whole value is an old roster token or old full name.
-- This intentionally catches linked user_profiles, settings, preferences, swaps, backup rows,
-- audit actor fields, research questionnaire respondent fields and similar identity columns.
do $$
declare rec record;
begin
  for rec in
    select col.table_schema,col.table_name,col.column_name
    from information_schema.columns col
    join information_schema.tables tbl on tbl.table_schema=col.table_schema and tbl.table_name=col.table_name and tbl.table_type='BASE TABLE'
    where col.table_schema='public'
      and col.data_type in ('text','character varying','character')
      and col.is_generated='NEVER'
      and not (col.table_name='resident_directory' and col.column_name='initials')
  loop
    execute format(
      'update %I.%I t set %I=m.new_initials from _v2599_roster_map m where t.%I=m.old_initials',
      rec.table_schema,rec.table_name,rec.column_name,rec.column_name
    );
    execute format(
      'update %I.%I t set %I=m.new_name from _v2599_roster_map m where t.%I=m.old_name',
      rec.table_schema,rec.table_name,rec.column_name,rec.column_name
    );
  end loop;
end $$;

-- Rewrite exact identity/name JSON string values (including object keys such as assignment maps)
-- in every public jsonb column without touching free-text substrings.
do $$
declare rec record; m record; expr text;
begin
  for rec in
    select col.table_schema,col.table_name,col.column_name
    from information_schema.columns col
    join information_schema.tables tbl on tbl.table_schema=col.table_schema and tbl.table_name=col.table_name and tbl.table_type='BASE TABLE'
    where col.table_schema='public' and col.data_type='jsonb'
  loop
    expr := format('%I::text',rec.column_name);
    for m in select * from _v2599_roster_map order by old_initials loop
      expr := format('replace(%s,%L,%L)',expr,'"'||m.old_initials||'"','"'||m.new_initials||'"');
      expr := format('replace(%s,%L,%L)',expr,'"'||m.old_name||'"','"'||m.new_name||'"');
    end loop;
    execute format(
      'update %I.%I set %I=(%s)::jsonb where %I is not null',
      rec.table_schema,rec.table_name,rec.column_name,expr,rec.column_name
    );
  end loop;
end $$;

-- Remove old parent keys only after all child rows have moved.
delete from public.resident_directory r
using _v2599_roster_map m
where r.initials=m.old_initials;

-- Any security/research RPC that hard-coded an old roster token is rewritten in place.
-- The function signature/permissions/dependencies stay unchanged.
do $$
declare f record; maprec record; def text;
begin
  for f in
    select p.oid
    from pg_proc p
    join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public'
      and p.prokind in ('f','p')
      and exists (
        select 1 from _v2599_roster_map mp
        where pg_get_functiondef(p.oid) like '%'||mp.old_initials||'%'
           or pg_get_functiondef(p.oid) like '%'||mp.old_name||'%'
      )
  loop
    def:=pg_get_functiondef(f.oid);
    for maprec in select * from _v2599_roster_map order by old_initials loop
      def:=replace(def,maprec.old_initials,maprec.new_initials);
      def:=replace(def,maprec.old_name,maprec.new_name);
    end loop;
    execute def;
  end loop;
end $$;

-- Final integrity assertions.
do $$
declare n integer;
begin
  select count(*) into n
  from public.resident_directory r
  join _v2599_roster_map m on r.initials=m.new_initials
  where r.full_name=m.new_name and r.active=true;
  if n<>16 then
    raise exception 'V2.5.99 roster migration incomplete: expected 16 mapped active residents, found %',n;
  end if;

  select count(*) into n
  from public.resident_directory r
  join _v2599_roster_map m on r.initials=m.old_initials;
  if n<>0 then
    raise exception 'V2.5.99 roster migration left % old resident_directory keys',n;
  end if;
end $$;
