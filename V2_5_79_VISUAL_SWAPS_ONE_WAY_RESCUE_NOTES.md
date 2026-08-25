# V2.5.79 — VISUAL SWAPS + ONE-WAY EMERGENCY RESCUE

## Normal bilateral swap UI
Live swap requests are now wide visual cards rather than bare text rows.

Each card shows:
- resident color badges using the existing PERSON_COLORS palette;
- resident initials + names;
- OFFERED shift and REQUESTED shift as separate visual tiles;
- incoming numbering (`1/3`, `2/3`, ...);
- database request ID;
- full-width ACCEPT / REJECT or CANCEL controls.

Backup swap requests receive the same numbered/color-coded treatment.

## Email on incoming request
After a NORMAL or BACKUP swap request is successfully stored in DB, the app sends
a best-effort operational email to the target resident's account email.

Normal swap email includes:
- requester initials/name;
- offered shift;
- requested shift;
- DB request number;
- portal link when configured.

The request is stored BEFORE email delivery is attempted. Therefore SMTP/email
failure can never roll back or invalidate the DB request. The proposer sees a clear
warning if DB succeeded but email failed.

Email attempts are written to the existing email_log with a request-specific kind.

## No jump into emergency after REQUEST SWAP
Normal request creation deliberately does NOT call `st.rerun()`.
The swap list is fetched later in the same Streamlit pass, so the new request
appears without forced scroll restoration.

The emergency workflow is also inside a separate COLLAPSED expander and is never
automatically opened by a normal swap.

## ONE-WAY EMERGENCY RESCUE
The old “Emergency swap” model was removed from the active UI because it was a
misnomer.

New self-recorded flow:
1. Logged-in resident selects their own CURRENT LOCATION.
2. CURRENT LOCATION must be a lower-priority optional post.
3. MOVING TO must be a same-day, same-block critical SPS RO / SPS UG post.
4. The UI shows the current target occupant as a colored RESCUED PERSON.
5. On confirmation:
   - mover is removed from CURRENT LOCATION;
   - source optional post becomes VACANT;
   - mover is assigned to MOVING TO;
   - RESCUED PERSON is released from target;
   - RESCUED PERSON is NOT moved into the old source post.

The implementation reuses the existing engine primitive
`apply_emergency_critical_transfer`, so source-vacating semantics are explicit.

Only ACTUAL changes. SYSTEM fairness, publication post matrix and post debt remain
frozen. New audit rows use kind=`emergency_rescue`. Historical bilateral
kind=`emergency_actual` rows remain visible only as clearly marked LEGACY records.

## Regression
Synthetic September 2026:
- generated SYSTEM schedule: HARD 0;
- found lower-priority CENTRO RO AM source for I.M.;
- found same-time critical SPS RO AM target occupied by D.G.;
- applied one-way rescue;
- CENTRO RO source became vacant;
- SPS RO target became I.M.;
- D.G. was NOT moved into source;
- one-way semantics PASS.

## Preservation
scheduler_engine.py is byte-identical to V2.5.78.
V2.5.77 Friday water-fill, V2.5.74 all-post water-fill, V2.5.73 Onko/exact
workload, V2.5.76 privacy, and V2.5.78 atomic accept/reject/status sync are unchanged.

No new Supabase schema migration is required.
