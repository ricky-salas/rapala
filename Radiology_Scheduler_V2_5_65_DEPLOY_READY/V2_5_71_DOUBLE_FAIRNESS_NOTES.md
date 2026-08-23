# V2.5.71 — DOUBLE FAIRNESS + SHIFT-LENGTH ALLOCATION

- Built directly on V2.5.69 + V2.5.70 workday-length setting.
- Preferred 6h/12h no longer changes the total group AM+PM double-day count.
- Phase 1 first solves a neutral double total, locks it, then redistributes that same pool by work-style preference.
- Monthly resident double-count spread is structurally capped at max-min <= 2.
- 6h/12h/mixed are symmetric schedule-shape SOFT signals below concrete monthly time-off/work-date requests.
- Phase 2 strongly prefers already-needed double-days to include SPS RO or SPS UG. Sunday duties are SPS RO.
- Onko RO remains a separate 9h FULL day and is not counted as an AM+PM double.
- No Supabase schema migration required; account_settings.shift_length_preference already exists.
