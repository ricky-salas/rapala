# V2.5.119 — Automatic phases + October FCFS dubliai

## Resident clock — Europe/Vilnius
For target month M, the cycle runs in the previous calendar month:
- day 1 00:00 → day 14 00:00: monthly preferences open;
- day 14 00:00 → day 16 00:00: resident pre-FINAL swap window;
- dublis self-selection remains open through the swap window until day 16 00:00;
- from day 16 00:00: resident preference/swap/dublis self-service is closed and missing mandatory dubliai are assigned at random among residents who still have none;
- SP/ŠR operator manual tools are independent from resident clock windows.

For October 2026 this means:
- preferences: 2026-09-01 00:00 → 2026-09-14 00:00;
- swaps + dublis self-selection: 2026-09-14 00:00 → 2026-09-16 00:00;
- senior review from 2026-09-16 00:00.

## Dubliai
- Active from October 2026.
- Exactly 16 theoretical weekend 6h slots, one per resident.
- FCFS while self-service is open.
- If a resident does not choose, one of the remaining slots is random-assigned after day 16 00:00.
- Dublis is not work and never affects normal wishes/workload/fairness.
- Senior/operator can override a dublis at any phase with an audit reason.
- October 2026 catalog: Oct 3/4, 10/11, 17/18, 24/25, AM + PM = 16 slots.
- The old October legacy/test claim was cleared because October dubliai had not actually been selected yet.

## Preference submission points
- #1 real submission earns 16 points, #2 earns 15, … #16 earns 1; deadline-zero gets 0.
- IMPORTANT correction: points earned for target month M are used to resolve SOFT conflicts in target month M+1, not in M.
- HARD, Cannot-work, admin weekend water-fill, Dream Team, structural fairness and higher SOFT layers stay above this tie-break.
- Existing October submissions were backfilled into the points ledger; those points will apply to November.

## Lifecycle implementation
- Server-side clock functions are authoritative; residents cannot extend windows from the UI.
- pg_cron job `v25119-auto-cycle-5min` runs the automatic cycle maintenance.
- Exact permission checks use `now()` in RPCs, so the five-minute cron cadence does not extend a resident deadline.
- A Python solver still has to produce a valid draft. If the senior generates during the swap/review phase, the app automatically freezes/activates that SYSTEM without a separate Open/Close stage button.
- If a valid draft already exists, opening the senior control page during the automatic swap/review phase auto-freezes it; no separate phase activation click is required.

## Email
Operational email is disabled in V2.5.119 and no longer gates schedule actions. RAPA mobile is intended to replace it with in-app/push notifications.
