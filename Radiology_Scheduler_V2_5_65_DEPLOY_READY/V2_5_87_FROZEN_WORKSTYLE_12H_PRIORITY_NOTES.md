# V2.5.87 — FROZEN WORKSTYLE INPUT + 12H PRIORITY PROOF

Root cause:
Live A.P. now has shift_length_preference=3, but the already-published September
SYSTEM request_snapshot contained 0 for A.P. and in fact 0 for all 16 residents.
That historical run therefore never received Aistė's current 12 h preference.

V2.5.87:
- new generations read current Settings first and freeze them into request_snapshot;
- SYSTEM/ACTUAL audit uses only that frozen request_snapshot;
- later Settings changes cannot retroactively create a false missed workstyle row;
- workstyle audit shows concrete 12 h, 6 h and Onko 9 h counts.

Prefer-12 h allocation:
- group double-day pool remains fixed by higher rules;
- no extra doubles are created;
- explicit prefer-12 h residents are prioritized within that same pool;
- the solver maximizes the minimum double count across the 12 h cohort, then their
  total double exposure, preventing one requester from being ignored while peers
  or neutral residents receive the scarce double-days.

Regression with exactly A.P., E.S., G.M. preferring 12 h:
- HARD 0
- Friday spread 1
- group doubles 4-5
- A.P. 5
- E.S. 5
- G.M. 5
- all three workstyle rows 100% / HONORED

Historical frozen0 regression:
- current workstyle may be 3
- frozen snapshot 0
- old SYSTEM audit generates no shift_length_preference row
- PASS: no retroactive false miss.

V2.5.86 Friday 0-1 proof and DELETE/UNDO are preserved.
No Supabase migration required.
