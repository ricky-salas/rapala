# V2.5.74 — ALL-POST STRUCTURAL WATER-FILL

The phase-2 post allocator now treats workplace equality as a structural SYSTEM rule, not a late cosmetic objective.

Once phase-1 work dates/blocks are fixed, all non-Onko post labels are solved jointly. Two-way swaps, three-way cycles and larger redistribution cycles are therefore handled implicitly.

For each post with T assignments and N residents, the first attempted corridor is floor(T/N)..ceil(T/N), raw max-min <=1.

Example: 38 Mammography assignments / 16 residents -> ten residents x2 and six residents x3. A 1-vs-3 pattern cannot remain when a valid relabeling can equalize it.

If <=1 is infeasible under higher HARD/date/block locks, <=2 and then <=3 may be tried only after the tighter corridor is mathematically proven infeasible. Timeout is not proof.

Onko is separate: exact workload, even 0/2/4... pairs, monthly spread <=2.

Voluntary ACTUAL swaps after publication are fairness-neutral: post fairness, US/Mammography exposure, modality diversity and SYSTEM water-fill do not block a mutually accepted swap. SYSTEM fairness stays frozen. Exact monthly workload and Onko parity remain hard.
