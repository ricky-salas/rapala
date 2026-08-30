# V2.5.108 — LIVE WISH COMPARISON

## Purpose
Makes the research comparison truly apples-to-apples for September 2026 and future known months. The REAL / AVAILABLE GPT + HUMAN schedule and MY ENGINE are validated against the exact same frozen resident wishes/HARD snapshot.

## Changes
- Fixed whole-workbook preflight crash: `name 'np' is not defined`.
- Added `LIVE APP WISHES / HARD — same selected month` as the recommended research input source.
- In live mode, no historical wishes Excel is needed. The app reads the selected month's current resident inputs from the database, previews them, hashes them, and freezes them at case lock.
- The hand-made schedule still comes from the uploaded Excel workbook and is parsed across all worksheets.
- Both comparator and engine Run 1 are revalidated against the exact same immutable frozen input snapshot.
- Added direct request-level comparison: active wishes, honored/missed counts, cannot-work violations, per-resident wish outcomes, and every request side-by-side.
- Locked XLSX export now includes `wish_summary_run1` and `wish_request_compare`.
- Research input snapshots now preserve structured request ledger, rest-credit choices, note, and cross-month safety-tail fields.

## No database migration
No Supabase schema migration is required. Existing locked research cases remain immutable and keep their original engine-version lock semantics.
