# V2.5.96 — MONTHLY BASELINE + LIVE ACTUAL FAIRNESS — NO CATCH-UP

## Locked behavior

1. SYSTEM generation starts each month from a clean current-month water-fill baseline. Prior fairness counts are deliberately zeroed before optimization.
2. Prior-month fairness history is audit-only. It does not steer weekend, Friday, double, holiday, Resident-HARD, Onko, or workplace allocation in a future month.
3. The historical post-debt / cumulative-catch-up mechanism is retired. The legacy Rule Profile field remains only for schema compatibility and is ignored by the engine.
4. SOFT preferences must fit inside SYSTEM water-fill. The former first-history-month weekend volunteer exception is disabled.
5. After publication, permitted manual overrides and bilateral swaps may break water-fill. The SYSTEM publication baseline remains immutable for audit.
6. ACTUAL fairness is recalculated from the current real schedule and displays the resulting monthly spreads/workplace exposure. No post-publication imbalance is normalized away.
7. Completed backup cover transfers the covered slot to `actual_backup` (or planned backup fallback) for ACTUAL fairness only when `completed_at` exists. Planned/activated standby alone does not transfer exposure.
8. Monthly SYSTEM-vs-ACTUAL history is retained for monitoring and research only; it creates no future debt.
9. Cross-month safety/spacing still follows ACTUAL reality: prior consecutive-weekend tail and prior last-day Onko state are retained because they are safety/spacing, not fairness catch-up.
10. No Supabase schema migration is required: SYSTEM and ACTUAL metrics are derived from existing `baseline_json`, `current_json`, and completed backup rows.
