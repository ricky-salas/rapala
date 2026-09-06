# V2.5.120 — LIVE COUNTDOWN + TWO-STAGE PUBLISH

## Purpose
Make the monthly lifecycle obvious to every resident while keeping time gates automatic and publication decisions explicit for SP/ŠR.

## Resident-visible clock
For automatic FCFS cycles every account sees an always-visible live countdown card:
- before opening: time until preference window opens;
- preferences: time until day 14 at 00:00 Europe/Vilnius;
- swaps: time until day 16 at 00:00 Europe/Vilnius;
- senior review: resident self-service closed, waiting for senior FINAL review;
- FINAL: final publication status.

The countdown ticks every second in the browser. Authorization remains server-side in Supabase/RPC; the JavaScript clock is display-only.

## Senior publication workflow
Time phases switch automatically, but publication does not.

1. `GENERATE / REBUILD` may be pressed repeatedly while searching for a better draft. This only saves a draft.
2. During the day-14 → day-16 swap phase, SP/ŠR explicitly presses `PASKELBTI PRELIMINARŲ IR ATIDARYTI REZIDENTŲ SWAPUS`. That freezes SYSTEM and creates ACTUAL; residents can then see the schedule and use pre-FINAL swaps until the server deadline.
3. At day 16 00:00 resident self-service closes automatically. Remaining backup slots are handled by the existing V2.5.119 automatic/random rule. SP/ŠR reviews and manually overrides ACTUAL as needed.
4. FINAL unlocks only in `senior_review`. SP/ŠR explicitly presses `PATVIRTINTI FINAL...`.

Thus the normal cycle has exactly two publication decisions: PRELIMINARY and FINAL. Generate/Rebuild is not publication.

## Manual senior authority
SP/ŠR manual ACTUAL tools are not disabled by resident lifecycle deadlines. Once a preliminary/ACTUAL exists, operator corrections remain available until FINAL. If preliminary was missed entirely, after day 16 the senior can freeze the chosen SYSTEM for FINAL review without reopening resident swaps.

## Email
The October+ FCFS lifecycle remains independent of SMTP/email. V2.5.120 adds no email requirement.

## Database
No new migration is required. V2.5.120 uses the server-authoritative V2.5.119 lifecycle timestamps already deployed.
