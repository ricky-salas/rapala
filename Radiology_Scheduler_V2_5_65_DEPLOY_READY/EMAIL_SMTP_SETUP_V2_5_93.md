# SMTP setup — V2.5.93

Real email requires SMTP credentials in the deployed Streamlit app. Do not put passwords in GitHub.

Recommended Streamlit Secrets format:

```toml
[smtp]
provider = "gmail"
host = "smtp.gmail.com"
port = 587
user = "YOUR_SENDER_EMAIL"
password = "YOUR_APP_PASSWORD"
from_email = "YOUR_SENDER_EMAIL"
use_tls = true
use_ssl = false
```

For Gmail, use a Google App Password rather than the normal account password.

Alternative legacy root names remain supported:
- `SCHEDULER_SMTP_HOST`
- `SCHEDULER_SMTP_PORT`
- `SCHEDULER_SMTP_USER`
- `SCHEDULER_SMTP_PASSWORD`
- `SCHEDULER_EMAIL_FROM`
- `SCHEDULER_SMTP_USE_TLS`
- `SCHEDULER_SMTP_USE_SSL`

After deployment, open Schedule Control → Email and SMTP readiness → Send SMTP test email. The next lifecycle phase stays blocked until SMTP passes configuration preflight and every active resident has a notification email.
