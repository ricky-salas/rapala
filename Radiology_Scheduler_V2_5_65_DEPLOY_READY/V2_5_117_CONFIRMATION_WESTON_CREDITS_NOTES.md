# V2.5.117 — CONFIRMATION + WESTON CREDITS

## Fix 1 — ŠR Grafiko tvirtinimas restored
The lifecycle/operator controls in `Grafikas` were accidentally tied to the Advanced UI flag for ŠR. That made `Grafiko tvirtinimas` disappear whenever ŠR used Simple mode even though the backend still treats ŠR as an authorized lifecycle operator.

V2.5.117 makes UI complexity independent of authorization:
- SP: schedule control in Simple and Advanced.
- ŠR: schedule control in Simple and Advanced.
- other residents: no operator controls.
- actions remain audited as the actual account; ŠR never impersonates SP.

## Fix 2 — Credits is operational, not advanced-only
`Kreditai` is now visible in both Simple and Advanced modes for all residents.

SP and ŠR also receive a mirrored WESTON balance in this tab from the same persistent click ledger:
- SP sees a negative balance/debt to ŠR.
- ŠR sees an equal positive receivable/gain from SP.
- lifetime total and selected-month increment are shown.

No new database table or migration is required; the existing WESTON ledger/RPC remains authoritative.
