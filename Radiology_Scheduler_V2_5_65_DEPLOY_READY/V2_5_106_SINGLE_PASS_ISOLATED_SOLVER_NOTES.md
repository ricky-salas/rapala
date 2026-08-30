# V2.5.106 — single-pass work pattern + isolated production solver

This release fixes the real September 2026 regeneration failure that still occurred in V2.5.105.

## Root cause confirmed

V2.5.105 used a staged work-pattern MILP whenever weekend positive-work requests were active. On the current September request set, the first Resident-HARD-only stage received a 6-second budget and returned **time limit / no incumbent**. That was not evidence of infeasibility, but the phase returned no pattern and the UI eventually showed the retry warning.

## V2.5.106 changes

- Work-pattern generation now uses **one lexicographically weighted MILP solve** instead of the blocking chain `Resident-HARD proof -> weekend volunteer lock -> neutral solve -> work-style redistribution`.
- Resident-HARD remains the dominant objective tier by a wide numeric margin.
- Weekend `Pageidauju dirbti` remains voluntary burden and is still preference-aware; volunteer minimum/total fulfilment sits below Resident-HARD and above ordinary SOFT.
- 6h / mixed / 12h work-style is now a **small single-pass tie-breaker** on the neutral positive double cost. It no longer launches a second full MILP and cannot by itself make an extra double profitable.
- Operational **Generate/Rebuild** and **Re-check/Improve** now run through `solver_runner.py` in a disposable child Python process.
- The parent Streamlit process has a hard watchdog (100 s first attempt, 130 s clean retry). A native solver stall can therefore be killed without freezing the app indefinitely.
- The child process receives only the frozen people/request snapshot and active rule profile; it does not write to Supabase. The existing draft is changed only after a verified `SolveResult(ok=True)` is returned.

## Constitutional rules unchanged

Exact workload targets, Onko even-pair allocation, Onko consecutive-day prohibition, ABSOLUTE/Resident-HARD semantics, backup-capacity reservation, SPS RO/SPS UG/weekend/Friday structural fairness, non-Onko post water-fill, and SYSTEM-vs-ACTUAL separation remain unchanged.

No database migration is required.
