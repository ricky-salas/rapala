# V2.5.100 — EMAIL LIFECYCLE + DURABLE OUTBOX

## Scope
Notification/configuration release only. Scheduler/solver behavior is intentionally unchanged from V2.5.99.

## Lifecycle
1. `preferences_open` — all active residents, one event per target month.
2. `preferences_reminder` — only residents whose monthly form is still missing; respects the resident reminder on/off and start-day setting; max one event per resident/day.
3. `swap_open` — emitted when the operator actually opens the preliminary swap window; personal preliminary ICS attached.
4. `final` — emitted on FINAL confirmation; personal final ICS attached.

## Delivery architecture
- Streamlit and the background worker share `notification_core.py`.
- One SMTP sender configuration.
- `notification_outbox` is durable and idempotent with `unique(event_key, initials)`.
- Direct lifecycle actions try SMTP immediately after queueing.
- A failed direct attempt remains in the outbox for retry.
- `notification_worker.py` creates automatic preference-stage events and retries pending/failed outbox rows.
- Bundled GitHub Actions workflow runs at 06:15 and 07:15 UTC daily so one run lands in the Lithuania morning across EET/EEST; deduplication makes the second run harmless.

## UI
- Simple Senior mode: compact ready/not-ready state, `CHECK CHANNEL`, `SEND TEST TO ME`, lifecycle delivery summary, `RETRY FAILED ONLY`.
- Advanced mode: host/port/from/login/security details and email-address audit.
- No password is displayed.

## Safety / anti-spam
- Reruns cannot resend an already-sent lifecycle event.
- Resend buttons target failed/blocked recipients only.
- The old separate `backup_claim_reminder` is not created by the V2.5.100 lifecycle reminder function.
- Existing non-lifecycle operational emails (specific swap request, backup activation, manual correction, late access) remain supported.

## Deployment prerequisites
- Apply `SUPABASE_MIGRATION_V2_5_100_NOTIFICATION_OUTBOX.sql` (already applied to the current Supabase project during build).
- Configure Streamlit `[smtp]` secrets.
- Configure GitHub Actions secrets for the background worker; never place `SUPABASE_SERVICE_ROLE_KEY` in app/client code.
- Ensure all 16 residents have notification email addresses before preliminary/FINAL publication.
