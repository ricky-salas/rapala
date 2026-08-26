-- V2.5.95 server-side deadline materialization
create extension if not exists pg_cron with schema extensions;

-- The live project contains:
-- public.preference_cutoff_v2595(year,month)
-- public.auto_submit_due_zero_preferences_v2595()
--
-- Cron job:
--   name: v2595-zero-preference-hourly
--   schedule: 0 * * * *
--   command: select public.auto_submit_due_zero_preferences_v2595();
--
-- The internal cron function is revoked from public/anon/authenticated and is intended
-- only for the database scheduler. The resident deadline itself is independently
-- enforced by save_my_preferences_v2595().
