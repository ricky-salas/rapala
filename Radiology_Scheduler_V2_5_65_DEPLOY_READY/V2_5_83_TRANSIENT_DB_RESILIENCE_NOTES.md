# V2.5.83 — TRANSIENT DB RESILIENCE + SWAP WRITE RECONCILIATION

## Observed production failure
After a resident clicked ACCEPT on swap request #7, Streamlit reran the whole script.
Before the button handler was reached, top-level startup code attempted to read:

`scheduler_rule_profiles`

via `db.get_active_rule_profile()`.

The HTTP connection then failed with `httpx.RemoteProtocolError`.
Because that exception was not classified as transient by the existing retry helper,
the entire Streamlit rerun crashed. One resident saw the traceback and the other saw
a blank/dark page.

Live DB verification after the incident showed:
- request #7 = pending
- therefore the ACCEPT handler never executed
- no swap was applied by that click.

## V2.5.83 read resilience
`_retry_db` now explicitly recognizes transient protocol/transport failures,
including:
- RemoteProtocolError
- protocol/read/connect errors
- peer closed connection
- connection reset / aborted
- incomplete response
- timeouts

Default retry policy is now 5 attempts with short exponential backoff.

### Active rule profile
The last successfully read active rule profile is cached in-process.
On a transient read failure:
1. retry;
2. use last-known-good cached profile if available;
3. if no safe cached profile exists, show a clear temporary DB error and STOP safely.

The app no longer falls through to an unhandled traceback/blank page.

A session-level last-known-good copy is also retained.

### Resident directory
The same last-known-good pattern is used for the resident directory.

## Swap write reconciliation
Normal ACCEPT / REJECT / CANCEL already use the atomic server-side
`respond_swap_request_v2578` RPC.

V2.5.83 additionally handles the ambiguous network case:
- Postgres may commit the action;
- HTTP response may be lost due to RemoteProtocolError.

If the RPC response is lost, the app re-reads the authoritative swap row.
It only treats the action as successful when:
- saved status matches the expected action; AND
- saved reason/meta matches the reason sent by this action.

If the row is still pending, the original network error is re-raised.
Therefore the UI cannot falsely claim an ACCEPT that was not committed.

## Engine
ENGINE_API_VERSION bumped to 2.5.83 only.
Scheduler logic is unchanged from V2.5.82 / V2.5.81.

No Supabase migration required.
