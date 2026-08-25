# V2.5.75 — PRE-PUBLICATION SUMMARY AUDIT

## Purpose
`Suvestinė / Summary` is now useful immediately after generation, before the senior publishes the schedule.

## Draft-first behavior
If a new draft exists and is not yet the frozen publication baseline, `Suvestinė` shows:

**JUODRAŠČIO SUVESTINĖ — DAR NEPASKELBTA**

The published operational schedule is not replaced by merely generating or reviewing the draft.

This remains true even when an older schedule is already published: if the senior generates a new candidate, `Suvestinė` prioritizes the pending new draft for audit while explicitly stating that the published schedule has not changed.

After publication, `Suvestinė` switches back to:

**SYSTEM SUVESTINĖ — PASKELBTA**

and uses the frozen SYSTEM publication baseline.

## All-resident request audit
Before publication the senior can see every resident in one table with:
- target and generated workload;
- RESIDENT HARD honored/requested;
- `Noriu laisvos` honored/requested;
- `Pageidauju dirbti` honored/requested;
- SOFT satisfaction %;
- overall request satisfaction %;
- workstyle match % when active;
- weekend count;
- doubles;
- Onko RO, SPS RO and SPS UG counts;
- number of scored missed requests;
- compact missed-request preview.

Rows are ordered so RESIDENT HARD losses and lower request satisfaction surface first.

## Exact request inspection
The senior can select any resident and inspect:
- every scored missed request;
- what the resident asked for;
- what the draft actually assigned;
- why it is counted as honored/missed;
- how to verify it against the grid;
- honored requests in a separate expander for spot-checking.

## Draft workplace / fairness audit
Before publication the same Summary also shows the DRAFT:
- HARD errors;
- monthly fairness;
- post imbalance;
- preference average;
- workplace matrix;
- post spreads and guardrails;
- workload metrics.

Draft backup columns are hidden because backup obligations are finalized at publish time.

## Safety / persistence
No scheduling engine mechanics changed in V2.5.75.
No database schema changed.
No publication behavior changed.
No automatic publish is introduced.

V2.5.74 all-post structural water-fill, V2.5.73 even Onko parity/exact workload, workstyle/double fairness, settings fixes and voluntary ACTUAL-swap policy are preserved unchanged.
