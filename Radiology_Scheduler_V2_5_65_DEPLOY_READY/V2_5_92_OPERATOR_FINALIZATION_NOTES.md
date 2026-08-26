# V2.5.92 — OPERATOR CONTROL + PRELIMINARY SWAPS + FINAL

## Locked lifecycle

The monthly workflow is intentionally simple:

1. **Generate SYSTEM** — private engine draft. No cohort email is sent.
2. **Private operator ACTUAL correction (optional)** — R.S., or R.Š. in Išplėstinis contingency mode, may freeze SYSTEM and manually swap any two filled assignments. SYSTEM remains unchanged for research; only ACTUAL changes.
3. **Publish preliminary schedule + resident swaps (optional)** — standard window is the previous month **14th 08:00 → 17th 00:00 Europe/Vilnius**. The preliminary cohort email is sent when this phase is activated.
4. **FINAL** — may be reached after the preliminary phase or directly from the private working schedule. Final validation runs, the current ACTUAL + backup snapshot is locked as FINAL, the cohort FINAL email is sent, and FINAL Excel becomes available for administration.

There is no separate mandatory "manual override phase". Operator manual correction remains available at every pre-FINAL state.

## Preference timing

Resident wishes are accepted through the previous month 13th inclusive, expressed in the UI as the exact cutoff **14th 00:00 Europe/Vilnius**. Existing per-resident reminder-start settings in Nustatymai remain active.

## Operator roles and identity isolation

- **R.S.** is the primary lifecycle operator.
- **R.Š.** has the same lifecycle / repair capability only through his own authenticated account, surfaced in **Išplėstinis** as a contingency/research path.
- Actions are audited under the actual `auth.uid()` and resident initials that performed them.
- There is no profile switch and no account impersonation. `current_identity_v2589()` and the hardened profile-claim rules remain unchanged.
- G.M. and all other residents remain resident-only.

## Manual operator correction

`Grafikas → Grafiko tvirtinimas` contains a permanent pre-FINAL manual correction tool. It:

- swaps any two currently filled assignments;
- does **not** require bilateral resident consent;
- still blocks true ACTUAL safety / operational HARD violations;
- requires an audit reason;
- records actor, timestamp, people, and slots in `manual_schedule_overrides`;
- automatically supersedes unresolved resident swap requests touching changed slots;
- refreshes backups / calendars;
- sends a professional correction email with updated `.ics` only to the two affected residents;
- can reverse a previously applied resident swap by swapping the current assignments back.

The first private manual correction freezes the engine SYSTEM baseline before ACTUAL changes, preventing research contamination.

## Emails

All lifecycle email copy is professional and concise.

### Preliminary publication
Subject: `Preliminarus <mėnuo> grafikas paskelbtas`

Residents are told the exact swap-request deadline and that FINAL will be announced separately.

### Manual operator correction
Subject: `<mėnuo> grafiko korekcija`

Only affected residents are notified and receive an updated `.ics`.

### Individual late access
The affected resident receives the exact expiry and request limit.

### FINAL
Subject: `Galutinis <mėnuo> grafikas paskelbtas`

The email states that the schedule has been published and submitted to administration and that ordinary / late swaps are closed. Each resident receives their FINAL `.ics`.

SMTP and resident-email preflight remain fail-closed for preliminary and FINAL activation.

## FINAL immutability

FINAL stores both:
- `final_json` — the exact ACTUAL schedule at confirmation;
- `final_backups` — the exact effective backup plan at confirmation.

The administration Excel is built from this immutable snapshot. Later force-majeure / emergency ACTUAL history does not rewrite the submitted FINAL snapshot.

## Database migration

Apply `SUPABASE_MIGRATION_V2_5_92_OPERATOR_FINALIZATION.sql`. The migration has already been applied to the linked Supabase project during development.
