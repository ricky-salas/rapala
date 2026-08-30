# V2.5.105 — resilient preference-aware solve

This release fixes the production regeneration failure seen with a feasible September request set after preference-aware weekend allocation was enabled.

## What changed

- Added bounded automatic retries to the two-phase generator.
- Replaced the heavy post-label rescue step in the primary path with a smaller structural post-assignment MILP.
- The post solver preserves the same ascending water-fill corridors and fails closed on timeout/unknown status instead of widening fairness.
- Existing drafts are preserved if a new verified candidate cannot be obtained.
- The UI no longer reports `ABSOLUTE HARD / COVERAGE FEASIBILITY FAILED` merely because the preference-aware primary model timed out.

## What did not change

- Weekend positive requests remain voluntary burden choices.
- Saturday and Sunday non-voluntary fairness remain separate.
- Exact workload, Onko parity, rest/safety and mandatory coverage stay HARD.
- Mammography remains last-fill and Onko-zero residents retain first-exposure priority among remaining Mammography slots.
- SYSTEM remains the immutable publication baseline; ACTUAL swaps may later widen raw spreads and create no next-month catch-up.
