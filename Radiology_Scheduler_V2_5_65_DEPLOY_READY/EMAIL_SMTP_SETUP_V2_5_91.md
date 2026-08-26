# Real email setup — V2.5.91

V2.5.91 uses SMTP for real resident email delivery. The application does not use Supabase's limited default Auth SMTP for operational schedule mail.

Configure the Streamlit deployment secrets/environment with your production mailbox/provider:

```
SCHEDULER_SMTP_HOST = "smtp.provider.example"
SCHEDULER_SMTP_PORT = "587"
SCHEDULER_SMTP_USER = "..."
SCHEDULER_SMTP_PASSWORD = "..."
SCHEDULER_SMTP_USE_TLS = "1"
SCHEDULER_EMAIL_FROM = "Shift Happens <scheduler@your-domain.example>"
SCHEDULER_PUBLIC_URL = "https://your-streamlit-app.example"
```

Do not commit real SMTP passwords into GitHub or this ZIP. Put them only in the deployment's secret manager.

R.S. cannot open the swap window unless SMTP readiness is detected and every active resident has an email stored in Nustatymai. This is intentional fail-closed behavior because the workflow requires real notification.
