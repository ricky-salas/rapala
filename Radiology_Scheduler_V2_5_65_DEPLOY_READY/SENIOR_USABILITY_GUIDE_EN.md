# V2.5.96 current rule

Every month starts from a clean SYSTEM water-fill baseline. After publication, allowed overrides/swaps/repairs may break that water-fill and ACTUAL fairness is recalculated from reality. History is audit-only and never creates next-month catch-up. Completed backup cover transfers fairness exposure only when the cover is marked completed.

# Senior Scheduler Usability and Audit Guide

## Purpose

The tool is not meant to replace senior judgment or require blind trust. It is meant to automate repetitive counting, rule reconciliation and fairness optimization, while leaving the senior scheduler with a short, evidence-based exception audit.

Core workflow:

**Generate → Audit tool statements → Correct only exceptions → Publish → Manage ACTUAL changes.**

## Pre-publication checks

1. **HARD / diagnostics:** zero TRUE ABSOLUTE HARD errors; every unavoidable Resident-HARD loss must identify resident, date, block, post and reason.
2. **Critical exposure:** SPS RO, SPS UG and weekend spread should be 0–1 and avoid unnecessary clustering.
3. **Workload:** inspect worst rolling-7 hours, doubles and disproportionate weekly burden.
4. **Preference audit:** spot-check 3–5 residents rather than recounting everyone.
5. **Schedule / Proof:** verify that summary tool statements match the actual SYSTEM grid.

## Tool statement spot-check

For each sampled resident, verify a few concrete tool statements such as:
- Resident-HARD x/y;
- SOFT-1 / SOFT-2;
- SPS RO count;
- SPS UG count;
- weekend count;
- one explicitly missed request and the assignment causing it.

If the tool says `SPS UG = 2`, the SYSTEM schedule / Post Matrix must show exactly two assignments. If it says a specific request was missed, the conflicting assignment must be identifiable.

## Do not publish when

- TRUE ABSOLUTE HARD is violated;
- mandatory SPS RO / SPS UG / weekend coverage is missing;
- critical spread exceeds 1 without explicit unavoidable-conflict diagnostics;
- a Resident-HARD loss is unexplained;
- preference / post / workload tool statements do not match the schedule;
- imported requests are clearly incomplete;
- overlap or feasibility conflicts exist.

## What is not automatically an error

- A SOFT preference may remain unmet because a higher-ranked fairness or HARD rule dominates it.
- A noncritical post may temporarily reach the allowed guardrail if the trade-off is justified and POST DEBT is carried forward.
- Voluntary swaps change ACTUAL, not the frozen SYSTEM fairness baseline.
- A sickness pull-down from an optional post to SPS leaves the SYSTEM baseline unchanged but recalculates ACTUAL workplace/fairness statistics from real work.

## Full monthly workflow

Prepare month → collect requests → generate complete draft → run five-minute audit → correct exceptions only → publish → use decentralized swaps / repairs → review SYSTEM vs ACTUAL at month-end.

## Measuring whether the tool actually saves work

Track active human review time, number of sessions, tool statement checks, verified tool statements, manual corrections, resident contacts and post-publication interventions.

The relevant comparison is not “did a human still review the schedule?” Human review should remain. The comparison is:

**manual construction + manual checking** versus **automated construction + focused audit + exception correction**.

## Accountability metric

**Tool statement verification accuracy = verified correct tool tool statements / all audited tool tool statements.**

Any mismatch is recorded as a system-quality finding rather than hidden.

## SYSTEM versus ACTUAL

- **SYSTEM:** the published algorithmic allocation and frozen fairness/research baseline.
- **ACTUAL:** the real schedule after voluntary swaps, sickness and operational repairs.

## V2.5.75 — Summary before publication

After `GENERATE`, the senior can immediately open `Summary`. Until the candidate is published, the page is explicitly labeled `DRAFT SUMMARY — NOT PUBLISHED`. It shows every resident's Resident-HARD, requested-off, prefer-to-work, overall satisfaction, workstyle, workload, doubles, weekends and critical-post metrics plus exact missed requests. If the result is unsatisfactory, return to `Generation` and improve/regenerate. The published schedule is unchanged until `PUBLISH / CONFIRM` is explicitly pressed.


### V2.5.79 ONE-WAY EMERGENCY RESCUE
 EMERGENCY RESCUE


The old “Emergency swap” name was a misnomer. The new model is a one-way operational rescue:

1. The resident who was actually moved selects their `CURRENT LOCATION`.
2. They select a same-time critical `MOVING TO` target (SPS RO / SPS UG).
3. The UI shows the colored `RESCUED PERSON` currently staffing that critical target.
4. On confirmation:
   - the mover is removed from the lower-priority optional source post;
   - CURRENT LOCATION becomes **vacant**;
   - the mover is assigned to MOVING TO;
   - the RESCUED PERSON is released from the target;
   - the rescued person is **not** moved into the mover's old post.

ACTUAL schedule and ACTUAL fairness change. The SYSTEM publication baseline remains frozen for audit; V2.5.96 has no post debt or future catch-up. New rescue audit entries use `CURRENT LOCATION → MOVING TO` and colored mover/rescued identities. Historical bilateral `emergency_actual` rows remain visible only as explicitly marked LEGACY records.
