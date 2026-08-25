-- V2.5.90 SINGLE-WINDOW ROLE TRANSFER
-- Operational leadership transfer:
-- G.M. -> resident
-- R.S. -> Seniūnė
-- R.Š. -> resident workload status; researcher/admin capabilities are app-level.
update public.resident_directory
set role='resident', target_adjustment=0
where initials='G.M.';

update public.resident_directory
set role='senior', target_adjustment=-2
where initials='R.S.';

update public.resident_directory
set role='resident', target_adjustment=0
where initials='R.Š.';
