# V2.5.89 — AUTH IDENTITY LOCK + UNLIMITED INVITE RETRIES

## Exact G.M. root cause

G.M.'s database binding was correct:
- G.M. auth user -> G.M.
- R.Š. auth user -> R.Š.

The bug was `db.current_profile()`:
it queried visible rows from `user_profiles` and used `.limit(1)` without filtering
by the authenticated user id.

Senior RLS intentionally allows a senior account to READ multiple resident profiles.
Therefore G.M., who has senior visibility, could receive the first visible profile
row (for example R.Š.) as if it were her own identity.

This was an identity lookup bug, not a corrupted G.M. binding.

## V2.5.89 identity constitution

`auth.uid()` is the only source of logged-in identity.

New dedicated server RPC:
`current_identity_v2589()`

It returns only:
`user_profiles.user_id = auth.uid()`.

The app additionally compares the returned user_id with the authenticated SDK user id.
Any mismatch stops the app fail-closed.

## One account <-> one resident

Existing database constraints already provide:
- PRIMARY KEY(user_id)
- UNIQUE(initials)

V2.5.89 also hardens `claim_resident_profile()`:
- if an auth user is already linked to resident X, it cannot be rebound to resident Y;
- even possession of another resident's invite code cannot change that binding;
- re-submitting the SAME resident binding is idempotent;
- a resident already claimed by another auth user remains unavailable.

## Session isolation

Streamlit now stores the authenticated UID identity marker.
If a different auth UID appears in the same browser/process session:
- prior resident-specific session state is cleared;
- the app is rebuilt from the new auth UID.

Logout clears all resident/session UI state, not only the Supabase client.

## Registration retries

The scheduler itself imposes NO registration-attempt count.

An invite is consumed only during successful resident profile linking,
after authentication exists.

Therefore failed signup attempts:
- do not consume the invite;
- do not lock the resident;
- may be retried later as many times as needed.

E.K. live verification after the failed email-rate-limit attempt:
- invite used = false
- used_at = null

Important provider boundary:
Supabase built-in SMTP has its own email rate limits.
The app cannot reset that hourly provider quota.
V2.5.89 detects the rate-limit error and explains that the invite remains unused
and the user may retry later.

Custom SMTP is still the correct production solution for removing the built-in
SMTP bottleneck.

## Live migration

`v2589_auth_identity_lock` applied successfully to production Supabase.

No scheduler/fairness behavior changed from V2.5.88.
