# V2.5.114 — WESTON debt mirror

This release changes only the playful WESTON accounting presentation. Scheduler, water-fill, Dream Team, backup and swap policies are unchanged from V2.5.113.

## Rule
- SP owns the Generate / Regenerate button.
- Every SP Generate / Regenerate click records exactly +1 WESTON in the existing persistent ledger.
- The same ledger is presented from two viewpoints:
  - **SP:** `WESTON debt to ŠR`.
  - **ŠR:** `WESTONs SP owes you` / personal WESTON gain.
- Lifetime and selected-month numbers are always identical on both sides because they are read from the same database ledger.
- No second counter is created, so SP debt and ŠR receivable cannot drift apart.

## Where it appears
- SP Generation screen: running debt and +1 confirmation after a click.
- SP Summary / personal statistics: lifetime debt + selected-month debt.
- ŠR Summary / personal statistics: lifetime amount owed + selected-month gain.
- Transparency / personal stats: mirrored counters for both SP and ŠR.
- Personal Calendar/Schedule: compact lifetime WESTON counter for both parties.

## Database
No migration is required. V2.5.114 reuses the V2.5.110 persistent ledger already migrated to canonical SP by V2.5.113.
