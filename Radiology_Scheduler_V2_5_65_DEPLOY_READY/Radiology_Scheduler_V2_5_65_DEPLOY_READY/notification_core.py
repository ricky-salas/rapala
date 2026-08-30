from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage
from typing import Callable, Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _truthy(value, default=False):
    if value is None or str(value).strip() == "":
        return bool(default)
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def smtp_config(getter: Optional[Callable[[str, str], str]] = None) -> dict:
    """Build one normalized SMTP config from a getter or environment."""
    getter = getter or (lambda name, default="": os.environ.get(name, default))
    provider = str(getter("SCHEDULER_SMTP_PROVIDER", "") or "").strip().lower()
    host = str(getter("SCHEDULER_SMTP_HOST", "") or "").strip()
    from_email = str(getter("SCHEDULER_EMAIL_FROM", "") or "").strip()
    user = str(getter("SCHEDULER_SMTP_USER", "") or "").strip()
    password = str(getter("SCHEDULER_SMTP_PASSWORD", "") or "")

    if not host and provider in ("gmail", "google"):
        host = "smtp.gmail.com"
    if not host and provider in ("outlook", "microsoft", "office365"):
        host = "smtp.office365.com"
    if not host and (user.lower().endswith("@gmail.com") or from_email.lower().endswith("@gmail.com")):
        host = "smtp.gmail.com"
    # One-system-sender configuration: for authenticated providers the login and
    # From address normally match, so allow either one to fill the other.
    if not user and from_email and (provider in ("gmail","google","outlook","microsoft","office365") or host in ("smtp.gmail.com","smtp.office365.com")):
        user = from_email
    if not from_email and user:
        from_email = user
    if password and (provider in ("gmail","google") or host == "smtp.gmail.com"):
        # Google displays App Passwords in groups; pasted spaces are not part of the secret.
        password = "".join(password.split())

    use_ssl = _truthy(getter("SCHEDULER_SMTP_USE_SSL", ""), False)
    raw_port = str(getter("SCHEDULER_SMTP_PORT", "") or "").strip()
    try:
        port = int(raw_port or (465 if use_ssl else 587))
    except Exception:
        port = 465 if use_ssl else 587
    use_tls = _truthy(getter("SCHEDULER_SMTP_USE_TLS", ""), not use_ssl)

    return {
        "provider": provider,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_email": from_email,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
    }


def smtp_missing(cfg: dict) -> list[str]:
    missing: list[str] = []
    if not str(cfg.get("host") or "").strip():
        missing.append("SMTP host")
    if not str(cfg.get("from_email") or "").strip():
        missing.append("from email")
    elif not EMAIL_RE.fullmatch(str(cfg.get("from_email") or "").strip()):
        missing.append("valid from email")
    host=str(cfg.get("host") or "").strip().lower()
    provider=str(cfg.get("provider") or "").strip().lower()
    requires_auth = provider in ("gmail","google","outlook","microsoft","office365") or host in ("smtp.gmail.com","smtp.office365.com")
    if requires_auth and not str(cfg.get("user") or "").strip():
        missing.append("SMTP login")
    if (requires_auth or str(cfg.get("user") or "").strip()) and not str(cfg.get("password") or ""):
        missing.append("SMTP password/app password")
    return missing


def smtp_probe(cfg: dict, timeout: int = 15) -> tuple[bool, str]:
    """Connect, negotiate security and authenticate; sends no email."""
    missing = smtp_missing(cfg)
    if missing:
        return False, "Missing: " + ", ".join(missing)
    try:
        smtp_cls = smtplib.SMTP_SSL if cfg.get("use_ssl") else smtplib.SMTP
        with smtp_cls(cfg["host"], int(cfg["port"]), timeout=timeout) as server:
            if cfg.get("use_tls") and not cfg.get("use_ssl"):
                server.starttls()
            if cfg.get("user"):
                server.login(cfg["user"], cfg.get("password") or "")
            code, message = server.noop()
            if int(code) >= 400:
                return False, f"SMTP NOOP returned {code}: {message!r}"
        return True, "SMTP connection and authentication succeeded"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def send_email(
    cfg: dict,
    to_addr: str,
    subject: str,
    body: str,
    *,
    ics_text: str | bytes | None = None,
    ics_name: str | None = None,
    timeout: int = 20,
) -> tuple[bool, str]:
    missing = smtp_missing(cfg)
    if missing:
        return False, "SMTP not configured: " + ", ".join(missing)
    to_addr = str(to_addr or "").strip()
    if not EMAIL_RE.fullmatch(to_addr):
        return False, "Invalid recipient email"

    msg = EmailMessage()
    msg["Subject"] = str(subject)
    msg["From"] = str(cfg["from_email"])
    msg["To"] = to_addr
    msg.set_content(str(body))
    if ics_text is not None:
        payload = ics_text.encode("utf-8") if isinstance(ics_text, str) else bytes(ics_text)
        msg.add_attachment(payload, maintype="text", subtype="calendar", filename=ics_name or "schedule.ics")

    try:
        smtp_cls = smtplib.SMTP_SSL if cfg.get("use_ssl") else smtplib.SMTP
        with smtp_cls(cfg["host"], int(cfg["port"]), timeout=timeout) as server:
            if cfg.get("use_tls") and not cfg.get("use_ssl"):
                server.starttls()
            if cfg.get("user"):
                server.login(cfg["user"], cfg.get("password") or "")
            server.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
