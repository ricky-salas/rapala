# Real email setup — V2.5.92

V2.5.92 uses SMTP for real operational resident notifications. Supabase Auth email is not used for schedule lifecycle mail.

Configure the Streamlit deployment secrets/environment:

```text
SCHEDULER_SMTP_HOST = "smtp.provider.example"
SCHEDULER_SMTP_PORT = "587"
SCHEDULER_SMTP_USER = "..."
SCHEDULER_SMTP_PASSWORD = "..."
SCHEDULER_SMTP_USE_TLS = "1"
SCHEDULER_EMAIL_FROM = "Shift Happens <scheduler@your-domain.example>"
SCHEDULER_PUBLIC_URL = "https://your-streamlit-app.example"
```

Never commit real SMTP passwords into GitHub or the ZIP. Keep them only in the deployment secret manager.

V2.5.92 sends real email for:
- preliminary schedule publication to the cohort;
- resident-to-resident swap requests;
- manual operator corrections to the two affected residents;
- individual late-access grants;
- FINAL publication to the cohort.

Preliminary and FINAL activation are fail-closed if SMTP is not configured or an active resident has no stored email. Manual operator correction is also blocked if either affected resident lacks an email, so a direct administrative correction cannot silently occur without notifying the affected people.
