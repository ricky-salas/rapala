# V2.5.93 — EMAIL ADMIN + SMTP PREFLIGHT + MANUAL OVERRIDE REVIEW

## Resident notification email administration
- R.S. and R.Š. lifecycle operators can fill missing resident notification emails from the schedule-control panel.
- `AUTOMATIŠKAI UŽPILDYTI IŠ PRISIJUNGIMO PASKYRŲ` copies only an already-bound login/profile email into `account_settings.email` when the notification email is blank.
- If no login/profile email exists, the operator can enter a notification email manually.
- This never changes `auth.uid()`, login credentials, profile binding, or resident identity.
- Every operator email change is written to `resident_email_admin_audit`.

## SMTP
V2.5.93 reads either legacy root secrets (`SCHEDULER_SMTP_*`) or a nested Streamlit Secrets block:

```toml
[smtp]
provider = "gmail"
host = "smtp.gmail.com"
port = 587
user = "scheduler@example.com"
password = "APP_PASSWORD_OR_SMTP_PASSWORD"
from_email = "scheduler@example.com"
use_tls = true
use_ssl = false
```

The password is never rendered in the UI. The operator sees host/port/from/security diagnostics and can send a real SMTP test email. Gmail host is also inferred from provider/user when appropriate. Port 465 + `use_ssl=true` is supported.

Important: SMTP credentials are deployment secrets and are deliberately not bundled inside the ZIP.

## Manual override review checkpoint
- Every new operator manual override stores BEFORE and AFTER snapshots.
- The change starts as `unreviewed`.
- Schedule Control displays a persistent before/after preview with affected shifts, operator, reason, and current HARD validation.
- PRELIMINARY publication and FINAL confirmation are blocked until every manual override is explicitly reviewed.
- The block is enforced in both Streamlit UI and Supabase RPCs.
- The checkpoint survives refresh/reboot.

## Identity security
V2.5.89 identity binding remains unchanged. Shared R.S./R.Š. capability does not create account switching or impersonation. Operator email administration changes notification destination only.
