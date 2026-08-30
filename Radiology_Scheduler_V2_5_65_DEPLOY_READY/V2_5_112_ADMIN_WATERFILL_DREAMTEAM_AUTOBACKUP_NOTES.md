# V2.5.112 — ADMIN WATER-FILL + DREAM TEAM + AUTO BACKUPS + SR GATE + WESTON

## Operational constitution
SYSTEM generation now follows the administrator-directed order:

1. TRUE ABSOLUTE safety / coverage rules.
2. RESIDENT HARD `Cannot work / Negaliu dirbti` — zero violations required.
3. ADMIN RAW weekend water-fill — resident weekend wishes cannot buy extra Saturdays/Sundays.
4. Dream Team rule — SR + ŠR + GE together on CENTRO RO at least once per represented workweek when mathematically feasible.
5. Workplace/post water-fill — SPS RO/SPS UG first, then every other workplace as tightly as feasible.
6. AUTO backup-duty (`dubliai / pavadavimai`) water-fill.
7. Remaining SOFT wishes and work-style preferences.

ACTUAL voluntary swaps may later disturb SYSTEM fairness, but only after both residents consent and SR gives final approval. Safety/operational blockers remain enforced.

## Weekend policy
- Weekend `Prefer to work` is audit-only for SYSTEM generation.
- Saturday, Sunday and total weekend exposure are evaluated on RAW assignments.
- The engine searches the tightest feasible weekend corridor before moving on.
- September 2026 regression: caps 1, 2 and 3 are infeasible with current HARD availability/exact workload; cap 4 is the tightest feasible overall weekend corridor.
- This does not mean every resident receives four weekends. It means max-minus-min weekend assignment exposure cannot be pushed below 4 under the current mandatory constraints.

## Workplace water-fill improvement
The post-placement search now checks the missing tight corridors instead of jumping from `(critical=1, ordinary=3)` directly to `(critical=2, ordinary=3)`.

September 2026 now reaches:
- SPS RO spread: 2
- SPS UG spread: 2
- CENTRO RO spread: 1
- Centro UG spread: 1
- ADC 144 spread: 1
- ADC 145 spread: 1
- Vaikų UG spread: 1
- Mamografijos spread: 1
- Onko remains under its separate even-pair constitution; observed spread 2.

The earlier V2.5.112 experimental candidate had ordinary-post spread 3; this final package improves that to 1 while keeping all five Dream Team weeks.

## Dream Team
Canonical database initials are `SR`, `ŠR`, and `GE`.

The post-placement phase maximizes a same-block CENTRO RO co-location for all three in each represented workweek. Morning or afternoon both count.

September 2026 regression: 5 / 5 represented weeks achieved.

## AUTO backups / dubliai
`Dubliai` here means named backup / cover duties, not AM+PM 12-hour workdays.

Required named-backup scope:
- SPS RO — every active day/block
- SPS UG — every active day/block
- Centro UG 120 — AM
- Onko RO — FULL

CENTRO RO is then used as safe best-effort filler to improve backup-load equality.

September 2026 regression:
- 126 mandatory named backup duties
- 32 CENTRO RO best-effort filler duties
- 158 total AUTO backup duties
- every resident receives backups
- resident backup load: 9–10
- backup spread: 1
- zero backup HARD errors

Generated backup duties are stored with the draft, appear in resident personal schedules, Summary statistics, and Excel/Backups export.

## 12-hour workdays vs backups
Statistics explicitly distinguish:
- `12h workdays (AM+PM)`
- `AUTO backup duties / dubliai`

They are no longer presented as the same concept.

## SR swap gate
Normal and backup voluntary swaps now use:

`Resident A proposes → Resident B accepts → WAITING FOR SR → SR APPROVE / DECLINE → ACTUAL changes`

SR sees the full pending queue. Resident acceptance alone never applies the swap.

## WESTON ledger
For SR only:
- every Generate / Regenerate button press records `+1 WESTON beer`
- displayed next to the Generate button
- persistent lifetime total and selected-month total appear in SR personal statistics

This is deliberately playful UI only and has no scheduling effect.

## Database
Production migration applied:
- `v2_5_112_weston_sr_swap_gate`

It provides the WESTON ledger plus exact-SR final approval fields/functions for voluntary swaps.
