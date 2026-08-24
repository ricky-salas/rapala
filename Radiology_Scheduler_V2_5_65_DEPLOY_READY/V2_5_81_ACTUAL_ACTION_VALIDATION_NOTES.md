# V2.5.81 — ACTUAL ACTION VALIDATION + EXPLICIT HARD REASONS

## Constitutional split
V2.5.81 makes the SYSTEM/ACTUAL boundary explicit.

SYSTEM generation still treats structural fairness as HARD:
- Friday raw spread <= 1;
- SPS/post water-fill rules;
- weekend structural rules;
- optional-gap distribution;
- generator fatigue shaping.

After publication, ACTUAL actions are different:
- normal bilateral swaps may worsen Friday spread;
- may worsen any workplace/post spread;
- may worsen double spread;
- backup swaps may worsen backup/double fairness;
- Emergency Rescue may create a new optional gap and worsen all fairness spreads.

These changes do NOT rewrite the frozen SYSTEM fairness baseline.

## The “no valid base version” bug
A historical published schedule could be revalidated against a newer generation
engine. Example: a schedule published under V2.5.73 could have Friday spread 3.
V2.5.77 later made Friday spread <=1 a SYSTEM-generation rule.

Previously:
CURRENT -> live generation revalidation -> result.ok=False ->
preview_swap -> “Nėra validžios bazinės versijos”.

This was wrong. The database schedule existed and was published; only a newer
generator-only fairness rule differed.

V2.5.81:
- CURRENT/ACTUAL revalidation uses `voluntary_swap_actual`;
- preview_swap no longer blindly rejects `result.ok=False`;
- if needed, it rechecks the existing CURRENT under ACTUAL operational rules;
- a legacy generator-only fairness mismatch does not block a swap.

## What still blocks a NORMAL bilateral swap
Only true non-relaxable ACTUAL constraints, including:
- exact monthly workload;
- even Onko parity;
- required Onko/mandatory clinical coverage;
- overlapping assignments;
- maximum 12h/day;
- maximum 6 workdays/rolling 7 days;
- ACTUAL absolute rolling-7-day hours ceiling (up to 60h);
- minimum 11h daily rest;
- mandatory post-duty rest;
- vacation / absolute justified absence;
- closed/blocked shifts;
- required backup availability.

Resident-HARD self-overrides and generator-only fairness/fatigue shaping remain
warnings/ACKs where previously allowed.

## Explicit HARD reason UI
If a swap is blocked, the user now sees:
- the exact HARD rule name;
- a plain-language explanation;
- the technical validator detail.

Examples:
- “Minimalus 11 val. paros poilsis”
- “Persidengiančios pamainos”
- “Tikslus mėnesio krūvis”
- “Onko porų taisyklė”
- “Maksimali darbo trukmė per 7 dienas”

The same explanation is used when proposing, receiving, and senior-finalizing.

## Emergency Rescue UI
Emergency Rescue is no longer collapsed.
It is an always-visible bordered operational panel with a large 3.1rem 🚨 beacon.

The visible heading is simply:
`EMERGENCY RESCUE`

Removed from the user-facing panel:
- “ne apsikeitimas”
- “Tai NĖRA swapas”
- “not a swap”

The colored CURRENT LOCATION -> MOVING TO -> RESCUED PERSON workflow is preserved.

## Regression
September 2026 neutral generation:
- SYSTEM HARD errors: 0
- SYSTEM Friday spread: 1
- ordinary post spreads: 1
- Onko spread: 2

Legacy-base regression:
- forced result.ok=False on an otherwise ACTUAL-valid published assignment map;
- preview_swap revalidated under ACTUAL rules;
- swap preview PASSED;
- no “base version” rejection.

Fairness freedom regressions:
- voluntary swap increased Friday spread 1 -> 2: ALLOWED, HARD=0;
- voluntary swap increased post spread (e.g. SPS UG 1 -> 3): ALLOWED, HARD=0;
- voluntary swap increased double spread 2 -> 3: ALLOWED, HARD=0.

True-HARD regression:
- Onko <-> ordinary invalid swap rejected;
- explicit rows included EXACT_MONTHLY_WORKLOAD and ONKO_EVEN_PARITY;
- no generator Friday/gap fairness appeared as a blocker.

No Supabase migration required.
