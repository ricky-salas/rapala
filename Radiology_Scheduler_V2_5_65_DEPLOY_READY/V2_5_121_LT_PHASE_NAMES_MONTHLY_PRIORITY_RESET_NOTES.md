# V2.5.121 — Lithuanian phase names + monthly priority reset

## Lifecycle wording
Resident-facing Lithuanian lifecycle labels were simplified to:

1. `1 etapas · Pageidavimų teikimas`
2. `2 etapas · Apsikeitimų laikotarpis`
3. `3 etapas · Seniūnės galutinė peržiūra`
4. `Galutinis grafikas paskelbtas`

Primary senior publication buttons are now:
- `1/2 — Paskelbti preliminarų grafiką`
- `2/2 — Patvirtinti galutinį grafiką`

The live second-by-second countdown and the automatic 1st/14th/16th time gates are unchanged.

## Monthly priority constitution
Priority is explicitly NON-CUMULATIVE.

- A submission race is independent for every schedule month.
- #1 earns 16 points, #2 earns 15, ... #16 earns 1; automatic deadline-zero earns 0.
- Editing later does not change the first-submission rank.
- Points earned while submitting preferences for schedule month M are used only in schedule month M+1.
- After that one schedule month, those points expire from solver influence.
- No summation across historical months is used.
- ADMIN/HARD/fairness tiers remain above preference priority; the rank is only a SOFT conflict resolver inside an already-locked fair frontier.

Senior preference statistics now show separately:
- priority applied to this schedule (from the previous cycle), and
- points earned for the next schedule (from the current submission race).
