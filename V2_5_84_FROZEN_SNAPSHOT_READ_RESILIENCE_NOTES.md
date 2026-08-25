# V2.5.84 — FROZEN-SNAPSHOT SWAP READ RESILIENCE

## Production failure fixed
The screenshot showed:

`httpx.ReadError`
`refresh_result_payload -> load_people -> db.all_recurring_preferences`

`all_recurring_preferences()` was still a direct Supabase read and bypassed the
V2.5.83 transient retry helper.

## Architectural correction
Published ACTUAL schedule revalidation no longer re-downloads the resident request
model on every Streamlit rerun when the schedule already contains the immutable
publication-time `request_snapshot`.

For published schedules:
- `people_for_stored_result()` restores Person objects directly from request_snapshot;
- normal swap preview uses that same frozen snapshot;
- incoming swap revalidation uses it;
- senior final swap apply uses it;
- backup-swap eligibility in the published schedule uses it;
- Emergency Rescue `refresh_result_payload()` uses it.

This is both more robust and methodologically correct: post-publication ACTUAL
validation should use the request set frozen with SYSTEM publication, not a newly
downloaded preference/settings/recurring model.

Legacy schedules without request_snapshot still fall back to live `load_people()`.

## DB read hardening
All recurring/load_people dependencies now use transient retry:
- all_preferences (already protected)
- all_account_settings (already protected)
- all_recurring_preferences (NEW)
- list_backup_claims (NEW)
- published_baselines_before (NEW)
- fairness_cumulative_before (NEW)

Additional operational Apsikeitimai reads now also retry:
- list_backup_swap_requests
- rest-credit reads
- open work-debt reads
- fairness-history display
- schedule-repair log

V2.5.83 transient classification/retry and lost-response swap reconciliation remain.

## Engine
ENGINE_API_VERSION = 2.5.84.
Scheduler logic is unchanged from V2.5.83; only the API marker changed.

No Supabase migration required.
