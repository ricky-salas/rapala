# V2.5.102 — persistent preferences + cleaner UI

- Settings are persistent across future, not-yet-frozen months until the resident changes them.
- Month-specific Preferences remain keyed to one target year/month and do not copy into the next month.
- Long-term recurring preferences remain persistent and are now edited in the Preferences tab, not Settings.
- Persistent weekday/weekend direction is restored as a real SOFT-3 work-style input.
- Weekend direction can only select the upper/lower layer inside the already locked Saturday/Sunday SYSTEM water-fill corridor; it cannot widen structural fairness.
- Preferred workday length (6h / mixed / 12h), holiday preference, distribution preference, notifications and calendar choices remain persistent account settings.
- Preference deadline card is shown only in the Preferences tab.
- User-facing `v3.0` badge is removed; internal release/API versioning remains.
- Lithuanian app title no longer contains “mėnesinio”.
- Reminder-start wording now explains that it controls personal countdown emails and includes an example.
- No Supabase migration is required: the existing account_settings, preferences and recurring_preferences schema already represents the three persistence scopes.
