# V2.5.88 — FAIRNESS-FIRST SYMMETRIC WORKSTYLE OPTIMIZATION

## Constitution

Workstyle modes do not outrank each other.

Order:
1. ABSOLUTE / safety / coverage HARD
2. structural fairness and exact SYSTEM workload
3. Resident-HARD and higher concrete monthly request priorities
4. establish the fair group double-day pool and allowed double spread
5. only then optimize long-term workstyle SOFT preferences

The long-term workstyle family is symmetric:
- prefer 6 h
- mixed 6 h / 12 h
- prefer 12 h

No intrinsic bonus is given to the 12 h mode.

## Why Aistė still gets 12 h

If Aistė prefers 12 h and moving existing fair double-days toward her does not
damage any higher-ranked rule or competing workstyle preference, the optimizer
should do it. She receives 12 h because it is an easy SOFT improvement inside the
already fair solution space, not because 12 h has a special rank.

## V2.5.87 correction

Removed the special prefer-12 h cohort-floor variable introduced in V2.5.87.

The fast work-pattern pass now uses equal-strength workstyle signals:
- prefer 6 h: +9 per double-day (avoid)
- prefer 12 h: -9 per double-day (seek)
- mixed: equal-magnitude deviation cost

The neutral group double total is still solved and frozen before any of these terms
are activated.

## Regression

September 2026, only A.P. prefers 12 h:
- HARD 0
- Friday spread 1
- group double range 4-5
- A.P. gets 5 double-days (group maximum)
- A.P. workstyle = 100% HONORED

Symmetry test:
- A.P. prefer 12 h
- E.S. prefer 6 h
- G.M. mixed
- HARD 0
- Friday spread 1
- policy = FAIRNESS_FIRST_THEN_SYMMETRIC_6H_MIXED_12H_SOFT
- no special 12 h floor exists

V2.5.87 frozen workstyle audit proof remains.
V2.5.86 Friday 0-1 and DELETE/UNDO remain.
No DB migration required.
