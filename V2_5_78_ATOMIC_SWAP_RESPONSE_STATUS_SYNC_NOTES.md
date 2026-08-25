# V2.5.78 — ATOMIC SWAP RESPONSE + STATUS SYNC

## What was observed
A normal swap request was rejected in the resident UI, while the other resident's
already-open page still displayed `pending`. A separate red screen showed
`email rate limit exceeded` on the Supabase Auth first-registration screen.

Live database verification showed that the normal swap row itself had actually
been saved as:
- status = rejected
- reason = declined
- responded_at populated

Therefore the original example combined two separate issues:
1. the swap response was persisted;
2. the other browser had stale UI state;
3. the email-rate-limit message belonged to Auth/signup, not the swap table.

## Hardening in V2.5.78

### Atomic normal swap response RPC
New production RPC:
`respond_swap_request_v2578(request_id, action, reason)`

Allowed actions:
- `accept`: target resident or senior only;
- `reject`: target resident or senior only;
- `cancel`: proposing resident or senior only.

The RPC:
- locks the swap row;
- requires current status = pending;
- authorizes the correct participant server-side;
- saves status/reason/responded_at atomically;
- returns the authoritative saved row.

The app verifies the returned status before reporting success.

### Normal cancel repaired
The app previously called `db.cancel_swap_request(...)` although no such wrapper
existed in db.py. V2.5.78 adds the wrapper and routes it through the atomic RPC.

### Backup cancel repaired
The app also called `db.cancel_backup_swap_request(...)` without a db.py wrapper.
V2.5.78 adds the wrapper to the existing secure Supabase RPC.

### Clear saved-state confirmation
After accept/reject/cancel, the app stores a flash message across `st.rerun()`
and explicitly reports the saved authoritative DB state.

### Manual DB refresh control
Swap UI now includes:
`↻ ATNAUJINTI SWAP STATUSĄ / REFRESH SWAP STATUS`

This makes the cross-browser behavior explicit: Streamlit pages do not push state
into another already-open browser. The other resident presses refresh (or causes
a normal rerun) to fetch the new DB state.

### Resilient reads
`get_swap_request` and `list_swap_requests` now use the existing transient DB retry
wrapper.

## Security
The new participant-response RPC is SECURITY DEFINER with explicit participant
authorization. PUBLIC execute is revoked; authenticated users only.

Anonymous execute was also revoked from the pre-existing normal and backup
cancel RPCs.

## Preservation
No scheduler engine logic changed.
V2.5.77 Friday water-fill, V2.5.74 all-post water-fill, V2.5.73 exact workload /
even Onko, and V2.5.76 privacy-safe summary are preserved.
