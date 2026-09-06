-- V2.5.122 — align weekend_backup_claims.source constraint with V2.5.118+ provenance values.
-- Safe compatibility migration: keeps legacy values and adds all current FCFS/random/operator sources.

alter table public.weekend_backup_claims
  drop constraint if exists weekend_backup_claims_source_check;

alter table public.weekend_backup_claims
  add constraint weekend_backup_claims_source_check
  check (source = any (array[
    'self'::text,
    'auto'::text,
    'senior'::text,
    'self_fcfs'::text,
    'auto_random'::text,
    'operator_manual'::text,
    'operator_manual_swap'::text
  ]));

comment on constraint weekend_backup_claims_source_check on public.weekend_backup_claims is
'Accepted provenance values for legacy and V2.5.118+ weekend backup assignment workflows.';
