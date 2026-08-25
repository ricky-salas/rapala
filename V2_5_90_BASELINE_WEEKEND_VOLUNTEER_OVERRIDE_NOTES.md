# V2.5.90 — SINGLE-WINDOW ROLE TRANSFER + BASELINE WEEKEND VOLUNTEERS

This package SUPERSEDES the earlier V2.5.90 SINGLE-WINDOW ROLE TRANSFER ZIP.

## Single-window account model

Every account has one visible interface and everyone gets:
- Paprastas
- Išplėstinis

Roles:
- R.S. = operational Seniūnė / leader, senior operational functions, target adjustment -2.
- R.Š. = one resident-facing account with embedded researcher + senior/admin capabilities, target adjustment 0.
- G.M. = ordinary resident only, no senior operational functions, target adjustment 0.
- Other residents = ordinary resident accounts.

V2.5.89 auth.uid() identity lock remains unchanged.

## Weekend / unpopular-duty volunteer rule

The old blanket rejection of recurring weekend SOFT has been split into two opposite meanings:

### Recurring weekend `Noriu laisvos`
Still rejected.
Reason: a blanket recurring wish to avoid weekends could shift unavoidable weekend burden to peers and bypass fairness.

### Recurring weekend `Pageidauju dirbti`
Now accepted.
This is interpreted as explicitly volunteering for an unpopular weekend duty.

## First-month baseline behavior

The volunteer override is active only when there is no prior published weekend history for the cohort.

Order:
1. ABSOLUTE HARD / safety / coverage
2. critical fairness of remaining burden
3. RESIDENT HARD
4. explicit baseline unpopular-weekend volunteers
5. temporal spacing / weekly load / remaining structural burden
6. normal SOFT / post optimization

An honored explicit weekend volunteer unit may be excluded from the CURRENT weekend and SPS RO fairness count.

The remaining NON-voluntary weekend/SPS RO burden must still remain water-filled at max-min <=1.

SPS UG and Friday structural rules remain unchanged.

## Whole-day semantics

A whole-day weekend `Pageidauju dirbti` means ONE voluntary day unit.

It does NOT mean the resident automatically requests both AM and PM.

If the schedule independently needs an additional half-day on the same date, that extra assignment is not hidden by the volunteer exemption and remains part of fairness/burden accounting.

## Multiple volunteers

When several residents volunteer for unpopular weekend work, the solver water-fills among the volunteer cohort:
- first raise the least-honored volunteer,
- then maximize total honored volunteer work,
- then use remaining fairness rules.

## Longitudinal fairness

The exception is deliberately baseline-only.

RAW actually worked weekend/SPS RO exposure is still:
- displayed,
- audited,
- stored in the published SYSTEM history.

Therefore later months remember that a volunteer already carried extra weekend burden and cumulative fairness resumes normally.

## Transparency

The audit exposes both:
- volunteer-adjusted fairness spread, used for the first-month structural gate;
- RAW visible spread, showing the actual physical weekend/SPS RO exposure.

A resident is never told that their real workload disappeared merely because they volunteered.

## If a volunteer request cannot be honored

If a higher rule prevents the engine from honoring an explicit weekend volunteer request, the resident-facing audit explains that the engine tried first but could not safely/validly place it.

The UI directs the resident to use the personal swap workflow after generation.

## Database

No new Supabase migration is required for this weekend-volunteer change.
The existing V2.5.90 role-transfer migration remains the only V2.5.90 database migration.
