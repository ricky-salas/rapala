# V2.5.70 — SHIFT-LENGTH WORKSTYLE

- Source baseline: GitHub V2.5.69 ONKO VOLUNTARY SWAP OVERRIDE / Shift Happens v3.0.
- New persistent personal setting at the top of Settings: 6h / mixed 6h+12h / 12h / no preference.
- 12h means AM+PM on one date. Onko RO remains separate 9h FULL.
- 6h preference strongly discourages doubles when feasible.
- 12h preference strongly encourages AM+PM doubles when feasible.
- Mixed mode explicitly minimizes imbalance between ordinary 6h single-shift days and 12h AM+PM double-days; it is not the same as neutral.
- Mandatory safety, exact workload, Onko even-pair/recovery and coverage constraints remain unchanged.
- Legacy avoid_doubles is kept for backward compatibility, but the four-way selector is the resident-facing source of truth.
- The value is not shown in group summary tables or to other residents; the generator consumes it as an individual setting.
- Current Supabase already contains account_settings.shift_length_preference (integer, default 0), so no new production schema migration was required.
