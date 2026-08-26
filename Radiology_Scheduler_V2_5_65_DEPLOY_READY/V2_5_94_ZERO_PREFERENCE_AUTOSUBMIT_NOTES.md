# V2.5.94 — deadline zero-preference auto-submit

After the exact monthly preference cutoff, an operator view by R.S. or R.Š. automatically creates a `preferences` row for every still-missing active resident.

The generated row contains:
- zero HARD unavailability;
- zero SOFT free/preferred dates;
- zero monthly credits;
- empty note;
- `submission_source = deadline_zero`;
- `submitted_at = exact cutoff`.

This is a formal submitted-with-zero-requests record, not a fabricated preference.

Senior/advanced preference table:
- `Pateikta = TAIP`;
- `Pateikimo būdas = Automatiškai — 0 pageidavimų`.

Existing resident submissions are preserved and never overwritten.
A later explicit resident save is marked `submission_source = resident`.

The RPC is restricted to lifecycle operators and enforces the cutoff server-side.
