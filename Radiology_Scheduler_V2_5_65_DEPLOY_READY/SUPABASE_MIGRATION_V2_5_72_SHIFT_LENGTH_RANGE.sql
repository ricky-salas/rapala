-- V2.5.72 Workstyle UI compatibility fix
-- Current UI/db code uses shift_length_preference:
-- 0 = no preference, 1 = prefer 6h, 2 = mixed, 3 = prefer 12h.

alter table public.account_settings
  drop constraint if exists account_settings_shift_length_preference_check;

alter table public.account_settings
  add constraint account_settings_shift_length_preference_check
  check (shift_length_preference between 0 and 3);
