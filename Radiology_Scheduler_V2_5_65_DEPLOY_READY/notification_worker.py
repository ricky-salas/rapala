from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo


from notification_core import smtp_config, smtp_missing, send_email

TZ = ZoneInfo("Europe/Vilnius")
DEADLINE_DAY = 13


def _next_month(d: date) -> tuple[int, int]:
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def _cycle_dates(year: int, month: int):
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    open_at = datetime(py, pm, 1, 8, 0, tzinfo=TZ)
    cutoff = datetime(py, pm, DEADLINE_DAY + 1, 0, 0, tzinfo=TZ)
    return open_at, cutoff


def _month_label(year: int, month: int) -> str:
    names = ["", "sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]
    return f"{year} m. {names[month]}"


def _public_url() -> str:
    return str(os.environ.get("SCHEDULER_PUBLIC_URL", "") or "").strip()


def enqueue_automatic_events(sb, now_lt: datetime, dry_run: bool = False) -> int:
    """Create due preference-stage events. Unique event keys make repeated cron runs safe."""
    year, month = _next_month(now_lt.date())
    open_at, cutoff = _cycle_dates(year, month)
    if now_lt < open_at or now_lt >= cutoff:
        return 0
    # Only enqueue morning lifecycle reminders. The workflow runs twice daily for DST safety.
    if now_lt.hour < 8:
        return 0

    residents = sb.table("resident_directory").select("initials,full_name,active").eq("active", True).execute().data or []
    settings_rows = sb.table("account_settings").select("initials,email,notifications_on,reminder_start_day").execute().data or []
    settings = {r["initials"]: r for r in settings_rows}
    prefs_rows = sb.table("preferences").select("initials").eq("year", year).eq("month", month).execute().data or []
    submitted = {r["initials"] for r in prefs_rows}
    public = _public_url()
    created = 0

    def enqueue(row: dict):
        nonlocal created
        if dry_run:
            print("DRY-RUN enqueue", row["event_key"], row["initials"])
            created += 1
            return
        existing = sb.table("notification_outbox").select("id,status,to_email").eq("event_key", row["event_key"]).eq("initials", row["initials"]).limit(1).execute().data or []
        if existing:
            cur=existing[0]
            # A missing address may be repaired later. Refresh unsent rows instead of
            # permanently freezing the original blocked state.
            if str(cur.get("status") or "") != "sent" and str(row.get("to_email") or "").strip():
                sb.table("notification_outbox").update({
                    "to_email":row["to_email"],"subject":row["subject"],"body":row["body"],
                    "status":"pending","last_error":None,"updated_at":datetime.now(timezone.utc).isoformat(),
                }).eq("id",cur["id"]).execute()
            return
        sb.table("notification_outbox").insert(row).execute()
        created += 1

    # Stage opening: one operational message to every active resident.
    for r in residents:
        ini = r["initials"]
        email = str(settings.get(ini, {}).get("email") or "").strip()
        body = (
            f"Sveiki,\n\nAtidarytas {_month_label(year, month)} grafiko pageidavimų etapas. "
            f"Pageidavimus pateikite iki {cutoff.strftime('%Y-%m-%d %H:%M')} Lietuvos laiku.\n"
        )
        if public:
            body += f"\nShift Happens: {public}\n"
        enqueue({
            "event_key": f"preferences_open:{year}-{month:02d}",
            "event_type": "preferences_open",
            "initials": ini,
            "target_year": year,
            "target_month": month,
            "scheduled_for": open_at.astimezone(timezone.utc).isoformat(),
            "to_email": email,
            "subject": f"{_month_label(year, month)} pageidavimai atidaryti",
            "body": body,
            "status": "pending" if email else "blocked",
            "last_error": "Missing notification email" if not email else None,
        })

    # Existing resident-specific reminder preference remains: once per day from chosen start day,
    # but only while the form is still missing. One consolidated reminder replaces duplicate backup reminders.
    today = now_lt.date()
    deadline_date = cutoff.date() - timedelta(days=1)
    for r in residents:
        ini = r["initials"]
        if ini in submitted:
            continue
        s = settings.get(ini, {})
        if not bool(s.get("notifications_on", True)):
            continue
        start_day = int(s.get("reminder_start_day") or 8)
        start_day = max(1, min(DEADLINE_DAY, start_day))
        start_date = date(cutoff.year, cutoff.month, start_day)
        if not (start_date <= today <= deadline_date):
            continue
        email = str(s.get("email") or "").strip()
        left = max(0, (deadline_date - today).days)
        if left == 0:
            subject = f"Šiandien paskutinė diena pateikti {_month_label(year, month)} pageidavimus"
        else:
            subject = f"Liko {left} d. pateikti {_month_label(year, month)} pageidavimus"
        body = (
            f"Sveiki,\n\nJūsų {_month_label(year, month)} pageidavimai dar nepateikti. "
            f"Terminas: {cutoff.strftime('%Y-%m-%d %H:%M')} Lietuvos laiku.\n"
        )
        if public:
            body += f"\nShift Happens: {public}\n"
        enqueue({
            "event_key": f"preferences_reminder:{year}-{month:02d}:{today.isoformat()}",
            "event_type": "preferences_reminder",
            "initials": ini,
            "target_year": year,
            "target_month": month,
            "scheduled_for": datetime.combine(today, time(8, 0), tzinfo=TZ).astimezone(timezone.utc).isoformat(),
            "to_email": email,
            "subject": subject,
            "body": body,
            "status": "pending" if email else "blocked",
            "last_error": "Missing notification email" if not email else None,
        })
    return created


def deliver_due(sb, cfg: dict, limit: int = 100, dry_run: bool = False) -> tuple[int, int]:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = (
        sb.table("notification_outbox")
        .select("*")
        .in_("status", ["pending", "failed"])
        .lte("scheduled_for", now_iso)
        .order("scheduled_for")
        .limit(limit)
        .execute().data
        or []
    )
    sent = failed = 0
    for row in rows:
        if not str(row.get("to_email") or "").strip():
            if not dry_run:
                sb.table("notification_outbox").update({"status": "blocked", "last_error": "Missing notification email", "updated_at": now_iso}).eq("id", row["id"]).execute()
            failed += 1
            continue
        if dry_run:
            print("DRY-RUN send", row["event_key"], row["initials"], row["to_email"])
            sent += 1
            continue
        attempts = int(row.get("attempt_count") or 0) + 1
        ok, detail = send_email(
            cfg,
            row["to_email"],
            row["subject"],
            row["body"],
            ics_text=row.get("ics_text"),
            ics_name=row.get("ics_name"),
        )
        payload = {
            "attempt_count": attempts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_error": detail or None,
        }
        if ok:
            payload.update({"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        else:
            payload.update({"status": "failed"})
            failed += 1
        sb.table("notification_outbox").update(payload).eq("id", row["id"]).execute()
    return sent, failed


def main():
    parser = argparse.ArgumentParser(description="Shift Happens notification worker")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    url = str(os.environ.get("SUPABASE_URL") or "").strip()
    key = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    cfg = smtp_config()
    missing = smtp_missing(cfg)
    if missing and not args.dry_run:
        raise SystemExit("SMTP configuration incomplete: " + ", ".join(missing))

    from supabase import create_client
    sb = create_client(url, key)
    now_lt = datetime.now(TZ)
    created = enqueue_automatic_events(sb, now_lt, dry_run=args.dry_run)
    sent, failed = deliver_due(sb, cfg, limit=max(1, args.limit), dry_run=args.dry_run)
    print(f"notification_worker: enqueued={created} sent={sent} failed={failed} now_lt={now_lt.isoformat()}")
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
