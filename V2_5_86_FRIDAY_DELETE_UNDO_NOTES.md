# V2.5.86 — FRIDAY 0–1 PROOF + SAFE DELETE / UNDO

## Friday structural rule

SYSTEM generation remains fail-closed on Friday fairness.

For every newly generated SYSTEM/research run:

- count every filled Friday assignment;
- compute total Friday assignments `T`;
- with `N` active residents compute `floor(T/N)` and `ceil(T/N)`;
- every resident must fall inside that exact floor/ceil corridor;
- therefore raw Friday max−min spread must be `<=1`;
- a generated candidate outside the corridor is invalid and cannot be treated as a successful V2.5.86 run.

September 2026 regression:

- total Friday assignments = 72;
- residents = 16;
- 72 / 16 = 4.5;
- exact structural entitlement = 4–5 Fridays each;
- fresh V2.5.86 result = eight residents with 4 and eight with 5;
- raw spread = 1;
- HARD errors = 0.

The live September published SYSTEM was created under an older engine and currently contains a legacy 4–7 Friday distribution (spread 3). It is not silently rewritten because published SYSTEM/research baselines are immutable. A fresh generation/regeneration under V2.5.86 produces 4–5.

Historical frozen research runs with Friday spread >1 remain historically intact, but the UI now marks them `LEGACY FRIDAY WATER-FILL INVALID` instead of presenting them as valid current-engine output.

## DELETE / UNDO

All three user-facing action types now have a visible two-step DELETE button:

1. Normal swap
2. Backup/double swap
3. Emergency Rescue

DELETE is not merely cosmetic.

### Normal swap

- pending / rejected / accepted-but-not-applied: deletes the request/history row only;
- already applied: attempts to restore both ACTUAL slots to their pre-swap owners;
- undo is refused if either slot changed again after the swap;
- backup plan is rebuilt in the same database transaction;
- successful delete removes the visible swap row.

### Backup/double swap

- pending / rejected: deletes the request/history row;
- accepted/applied: restores the two previous backup holders;
- undo is refused if the backup was later activated, completed, manually overridden or changed again.

### Emergency Rescue

- DELETE / UNDO restores the mover to the previous CURRENT LOCATION;
- restores the RESCUED PERSON to the previous critical target;
- only if the source is still vacant and target still contains the mover;
- if either slot changed after the Rescue, undo is refused;
- backup plan is rebuilt atomically.

## Audit preservation

Deleted visible actions are copied to the new private `schedule_action_deletions` audit table before the original user-facing row is deleted. The user can correct an accidental action without destroying the forensic audit trail.

## Live database

Migration `v2586_delete_undo_actions` was applied to production Supabase.

New SECURITY DEFINER functions:

- `delete_swap_action_v2586`
- `delete_backup_swap_v2586`

Bundled migration:
`SUPABASE_MIGRATION_V2_5_86_DELETE_UNDO_ACTIONS.sql`
