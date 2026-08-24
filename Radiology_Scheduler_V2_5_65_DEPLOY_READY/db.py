from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional
import time
import secrets

_client = None
_default_manuals = {"LT": "", "EN": ""}


def set_client(client):
    global _client
    _client = client


def client():
    if _client is None:
        raise RuntimeError("Supabase client is not configured for this session")
    return _client


def _data(resp):
    return getattr(resp, "data", None) or []


def _is_transient_db_error(exc: Exception) -> bool:
    """Classify short-lived network/protocol failures from Supabase/httpx/postgrest."""
    msg=str(exc).lower()
    cls=exc.__class__.__name__.lower()
    mod=getattr(exc.__class__,"__module__","").lower()
    return (
        cls in {"remoteprotocolerror","readerror","connecterror","connecttimeout","readtimeout","writetimeout","pooltimeout"}
        or "remoteprotocolerror" in cls
        or "protocolerror" in cls
        or "httpx" in mod and any(x in cls for x in ("read","connect","timeout","protocol"))
        or "resource temporarily unavailable" in msg
        or "readerror" in msg
        or "connecterror" in msg
        or "timed out" in msg
        or "timeout" in msg
        or "server disconnected" in msg
        or "peer closed connection" in msg
        or "connection reset" in msg
        or "connection aborted" in msg
        or "incomplete message" in msg
        or "remote protocol" in msg
    )


def _retry_db(fn, attempts: int = 5, base_delay: float = 0.20):
    """Retry transient Supabase/httpx failures with short exponential backoff."""
    last=None
    for attempt in range(max(1,int(attempts))):
        try:
            return fn()
        except Exception as exc:
            last=exc
            if (not _is_transient_db_error(exc)) or attempt>=int(attempts)-1:
                raise
            time.sleep(float(base_delay)*(2**attempt))
    raise last


def _now():
    return datetime.now(timezone.utc).isoformat()


_ACTIVE_RULE_PROFILE_CACHE: Optional[dict] = None
_DIRECTORY_CACHE: Optional[Dict[str, dict]] = None


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None


def init_db(default_manual_lt: str, default_manual_en: str, default_people: list[dict]):
    # Schema is managed by Supabase migrations. Keep bundled manuals as fallback.
    _default_manuals["LT"] = default_manual_lt
    _default_manuals["EN"] = default_manual_en


def current_profile() -> Optional[dict]:
    rows = _data(_retry_db(lambda: client().table("user_profiles").select("user_id,initials,email,approved,preferred_language,access_role").limit(1).execute()))
    return rows[0] if rows else None


def auth_user_id():
    p=current_profile()
    return p.get("user_id") if p else None


def directory() -> Dict[str, dict]:
    global _DIRECTORY_CACHE
    try:
        rows = _data(_retry_db(lambda:
            client().table("resident_directory")
            .select("initials,full_name,role,target_adjustment,color,active")
            .eq("active", True)
            .execute()
        ))
        data={r["initials"]:r for r in rows}
        if data:
            _DIRECTORY_CACHE={k:dict(v) for k,v in data.items()}
        return data
    except Exception:
        if _DIRECTORY_CACHE is not None:
            return {k:dict(v) for k,v in _DIRECTORY_CACHE.items()}
        raise


def claim_profile(initials: str, invite_code: str) -> dict:
    rows = _data(client().rpc("claim_resident_profile", {"p_initials": initials, "p_invite_code": invite_code}).execute())
    return rows[0] if rows else {}


def claim_observer_profile(invite_code: str) -> dict:
    rows = _data(client().rpc("claim_observer_profile", {"p_invite_code": invite_code}).execute())
    return rows[0] if rows else {}


def save_preference(year: int, month: int, initials: str, payload: dict):
    old = get_preference(year, month, initials) or {}
    row = {
        "year": int(year), "month": int(month), "initials": initials,
        "unavailable": sorted(payload.get("unavailable", [])),
        "unavailable_am": sorted(payload.get("unavailable_am", [])),
        "unavailable_pm": sorted(payload.get("unavailable_pm", [])),
        "justified_absence": sorted(payload.get("justified_absence", [])),
        "vacation": sorted(payload.get("vacation", [])),
        "long_duty": sorted(payload.get("long_duty", [])),
        "soft_free": sorted(payload.get("soft_free", [])),
        "soft_free_am": sorted(payload.get("soft_free_am", [])),
        "soft_free_pm": sorted(payload.get("soft_free_pm", [])),
        "preferred": sorted(payload.get("preferred", [])),
        "preferred_am": sorted(payload.get("preferred_am", [])),
        "preferred_pm": sorted(payload.get("preferred_pm", [])),
        "note": payload.get("note", ""),
        "prior_weekend_count": int(old.get("prior_weekend_count", payload.get("prior_weekend_count", 0))),
        # V2.5.5: old generic credit selector is frozen at zero.
        "backup_credits_to_use": 0,
        "backup_credits_am_to_use": int(payload.get("backup_credits_am_to_use", old.get("backup_credits_am_to_use", 0))),
        "backup_credits_pm_to_use": int(payload.get("backup_credits_pm_to_use", old.get("backup_credits_pm_to_use", 0))),
        "backup_credits_night_to_use": 0,
        "updated_at": _now(),
    }
    client().table("preferences").upsert(row, on_conflict="year,month,initials").execute()


def set_prior_weekend_count(year: int, month: int, initials: str, count: int):
    old = get_preference(year, month, initials) or {}
    save_preference(year, month, initials, {**old, "prior_weekend_count": int(count)})


def _pref_from_row(row):
    return {
        "unavailable": set(row.get("unavailable") or []),
        "unavailable_am": set(row.get("unavailable_am") or []),
        "unavailable_pm": set(row.get("unavailable_pm") or []),
        "justified_absence": set(row.get("justified_absence") or []),
        "vacation": set(row.get("vacation") or []),
        "long_duty": set(row.get("long_duty") or []),
        "soft_free": set(row.get("soft_free") or []),
        "soft_free_am": set(row.get("soft_free_am") or []),
        "soft_free_pm": set(row.get("soft_free_pm") or []),
        "preferred": set(row.get("preferred") or []),
        "preferred_am": set(row.get("preferred_am") or []),
        "preferred_pm": set(row.get("preferred_pm") or []),
        "note": row.get("note", ""),
        "prior_weekend_count": int(row.get("prior_weekend_count", 0)),
        "backup_credits_to_use": 0,
        "backup_credits_am_to_use": int(row.get("backup_credits_am_to_use", 0)),
        "backup_credits_pm_to_use": int(row.get("backup_credits_pm_to_use", 0)),
        "backup_credits_night_to_use": int(row.get("backup_credits_night_to_use", 0)),
        "updated_at": row.get("updated_at", ""),
    }


def get_preference(year: int, month: int, initials: str) -> Optional[dict]:
    rows = _data(_retry_db(lambda: client().table("preferences").select("*").eq("year", int(year)).eq("month", int(month)).eq("initials", initials).limit(1).execute()))
    return _pref_from_row(rows[0]) if rows else None


def all_preferences(year: int, month: int) -> Dict[str, dict]:
    rows = _data(_retry_db(lambda: client().table("preferences").select("*").eq("year", int(year)).eq("month", int(month)).execute()))
    return {r["initials"]: _pref_from_row(r) for r in rows}


def get_account_settings(initials: str) -> dict:
    rows = _data(_retry_db(lambda: client().table("account_settings").select("*").eq("initials", initials).limit(1).execute()))
    if not rows:
        return {"email":"", "weekday_preference":0, "weekend_preference":0, "holiday_preference":0, "spread_preference":0,
                "shift_length_preference":0, "avoid_doubles":False, "notifications_on":True, "reminder_start_day":8,
                "preferred_language":"LT", "include_backups_in_calendar":False,
                "backup_email_alerts":True, "phone_e164":"", "backup_sms_alerts":False,
                "calendar_feed_token":"", "updated_at":""}
    r = rows[0]
    r["holiday_preference"] = max(-1,min(1,int(r.get("holiday_preference",0) or 0)))
    r["shift_length_preference"] = max(0,min(3,int(r.get("shift_length_preference",0) or 0)))
    # Preserve old residents who had only the legacy "avoid doubles" checkbox.
    if r["shift_length_preference"] == 0 and bool(r.get("avoid_doubles", False)):
        r["shift_length_preference"] = 1
    r["avoid_doubles"] = bool(r.get("avoid_doubles", False))
    r["notifications_on"] = bool(r.get("notifications_on", True))
    r["include_backups_in_calendar"] = bool(r.get("include_backups_in_calendar", False))
    r["backup_email_alerts"] = bool(r.get("backup_email_alerts", True))
    r["backup_sms_alerts"] = bool(r.get("backup_sms_alerts", False))
    r["phone_e164"] = r.get("phone_e164") or ""
    return r


def all_account_settings() -> Dict[str, dict]:
    rows = _data(_retry_db(lambda: client().table("account_settings").select("*").execute()))
    return {r["initials"]: {
        **r,
        "holiday_preference": max(-1,min(1,int(r.get("holiday_preference",0) or 0))),
        "shift_length_preference": (1 if max(0,min(3,int(r.get("shift_length_preference",0) or 0)))==0 and bool(r.get("avoid_doubles",False)) else max(0,min(3,int(r.get("shift_length_preference",0) or 0)))),
        "avoid_doubles": bool(r.get("avoid_doubles", False)),
        "notifications_on": bool(r.get("notifications_on", True)),
        "include_backups_in_calendar": bool(r.get("include_backups_in_calendar", False)),
        "backup_email_alerts": bool(r.get("backup_email_alerts", True)),
        "backup_sms_alerts": bool(r.get("backup_sms_alerts", False)),
        "phone_e164": r.get("phone_e164") or "",
    } for r in rows}


def save_account_settings(initials: str, payload: dict):
    row = {
        "initials": initials,
        "email": payload.get("email", "").strip(),
        "weekday_preference": int(payload.get("weekday_preference", 0)),
        "weekend_preference": int(payload.get("weekend_preference", 0)),
        "holiday_preference": max(-1,min(1,int(payload.get("holiday_preference",0) or 0))),
        "spread_preference": int(payload.get("spread_preference", 0)),
        "shift_length_preference": max(0,min(3,int(payload.get("shift_length_preference",0) or 0))),
        "avoid_doubles": bool(payload.get("avoid_doubles", False)),
        "notifications_on": bool(payload.get("notifications_on", True)),
        "reminder_start_day": int(payload.get("reminder_start_day", 8)),
        "preferred_language": payload.get("preferred_language", "LT"),
        "include_backups_in_calendar": bool(payload.get("include_backups_in_calendar", False)),
        "backup_email_alerts": bool(payload.get("backup_email_alerts", True)),
        "phone_e164": (payload.get("phone_e164") or "").strip() or None,
        "backup_sms_alerts": bool(payload.get("backup_sms_alerts", False)),
        "updated_at": _now(),
    }
    client().table("account_settings").update({k:v for k,v in row.items() if k!="initials"}).eq("initials",initials).execute()


def ensure_calendar_feed_token(initials: str) -> str:
    """Create one unguessable bearer token for the resident's public read-only ICS feed."""
    current=get_account_settings(initials)
    token=str(current.get("calendar_feed_token") or "").strip()
    if token:
        return token
    token=secrets.token_hex(32)
    client().table("account_settings").update({"calendar_feed_token":token,"updated_at":_now()}).eq("initials",initials).execute()
    return token


def publish_calendar_feed(initials: str, ics_bytes: bytes) -> str:
    """Publish/update an unguessable read-only ICS subscription feed in Supabase Storage."""
    uid=auth_user_id()
    if not uid:
        raise RuntimeError("Authenticated user required for calendar feed")
    token=ensure_calendar_feed_token(initials)
    path=f"feeds/{token}.ics"
    bucket=client().storage.from_("calendar-feeds")
    options={"content-type":"text/calendar; charset=utf-8","upsert":"true","cache-control":"300"}
    try:
        bucket.upload(path,ics_bytes,options)
    except Exception:
        # Older storage-py versions may reject upsert in upload; update existing object.
        bucket.update(path,ics_bytes,{"content-type":"text/calendar; charset=utf-8","cache-control":"300"})
    url=bucket.get_public_url(path)
    return str(url)


def get_recurring_preferences(initials: str) -> List[dict]:
    return _data(client().table("recurring_preferences").select("*").eq("initials", initials).order("weekday").execute())


def all_recurring_preferences() -> Dict[str, List[dict]]:
    rows = _data(_retry_db(lambda:
        client().table("recurring_preferences")
        .select("*")
        .order("initials")
        .order("weekday")
        .execute()
    ))
    out: Dict[str, List[dict]] = {}
    for r in rows:
        out.setdefault(r["initials"], []).append(r)
    return out


def save_recurring_preferences(initials: str, rows: List[dict]):
    # User owns these rows under RLS. Replace the seven-day pattern atomically enough for beta use.
    client().table("recurring_preferences").delete().eq("initials", initials).execute()
    payload=[]
    for r in rows:
        typ = r.get("preference_type")
        if not typ or typ == "none":
            continue
        block = r.get("block", "FULL") if typ == "hard_unavailable" else "FULL"
        payload.append({"initials": initials, "weekday": int(r["weekday"]), "preference_type": typ,
                        "block": block, "active": True, "updated_at": _now()})
    if payload:
        client().table("recurring_preferences").insert(payload).execute()


def save_draft(year: int, month: int, payload: dict):
    existing = _data(client().table("schedules").select("baseline_json,current_json,status,published_at").eq("year",year).eq("month",month).limit(1).execute())
    row={"year":year,"month":month,"draft_json":payload,"updated_at":_now()}
    if existing:
        row.update({k: existing[0].get(k) for k in ("baseline_json","current_json","status","published_at")})
    else:
        row["status"]="draft"
    client().table("schedules").upsert(row,on_conflict="year,month").execute()


def publish_draft(year: int, month: int) -> bool:
    rows = _data(client().table("schedules").select("draft_json").eq("year",year).eq("month",month).limit(1).execute())
    if not rows or not rows[0].get("draft_json"):
        return False
    draft=rows[0]["draft_json"]
    client().table("schedules").update({"baseline_json":draft,"current_json":draft,"status":"published","updated_at":_now(),"published_at":_now()}).eq("year",year).eq("month",month).execute()
    return True


def save_current(year: int, month: int, payload: dict):
    client().table("schedules").update({"current_json":payload,"updated_at":_now()}).eq("year",year).eq("month",month).execute()



def reset_month_schedule(year: int, month: int) -> dict:
    """Senior-only destructive reset of generated/published schedule outputs.

    Preserves resident preferences/constraints and credit redemptions so the month
    can be regenerated from the same input. The server RPC also blocks reset if
    completed backup-cover activity already exists for the month.
    """
    res = client().rpc(
        "reset_month_schedule_v2522",
        {"p_year": int(year), "p_month": int(month)}
    ).execute()
    data = getattr(res, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {"ok": True, "year": int(year), "month": int(month)}

def load_schedule(year: int, month: int, kind: str = "current") -> Optional[dict]:
    col={"current":"current_json","baseline":"baseline_json","draft":"draft_json"}.get(kind,"current_json")
    rows=_data(_retry_db(lambda: client().table("schedules").select(f"{col},status").eq("year",year).eq("month",month).limit(1).execute()))
    if not rows:
        return None
    if kind in ("current","baseline") and rows[0].get("status") != "published":
        return None
    return rows[0].get(col)


def list_published_schedules() -> List[dict]:
    """Return all published ACTUAL schedule payloads for calendar-feed assembly."""
    rows = _data(_retry_db(lambda: client().table("schedules")
        .select("year,month,current_json,status,published_at,updated_at")
        .eq("status", "published")
        .order("year")
        .order("month")
        .execute()))
    return [r for r in rows if r.get("current_json")]


def get_schedule_state(year: int, month: int) -> dict:
    rows=_data(_retry_db(lambda: client().table("schedules").select("draft_json,baseline_json,current_json,status,published_at,updated_at").eq("year",year).eq("month",month).limit(1).execute()))
    if not rows:
        return {"has_draft":False,"has_published":False,"status":"none","published_at":None,"updated_at":None}
    r=rows[0]
    return {"has_draft":bool(r.get("draft_json")),"has_published":r.get("status")=="published" and bool(r.get("current_json")),"status":r.get("status"),"published_at":r.get("published_at"),"updated_at":r.get("updated_at")}


def create_swap_request(year: int, month: int, slot_a: int, slot_b: int, person_a: str, person_b: str, reason: str = ""):
    row={"year":year,"month":month,"slot_a":slot_a,"slot_b":slot_b,"person_a":person_a,"person_b":person_b,"status":"pending","reason":str(reason or ""),"created_at":_now()}
    return _data(client().table("swap_requests").insert(row).execute())


def apply_emergency_rescue_atomic_v2585(
    year: int, month: int, source_slot: int, target_slot: int,
    mover: str, rescued_person: str, current_payload: dict,
    desired_backups: List[dict], reason: str = ""
) -> dict:
    """Atomically apply ACTUAL rescue + backup-plan sync + audit on the server."""
    payload={
        "p_year":int(year),"p_month":int(month),
        "p_source_slot":int(source_slot),"p_target_slot":int(target_slot),
        "p_mover":str(mover),"p_rescued_person":str(rescued_person),
        "p_current_json":current_payload,
        "p_backups":list(desired_backups or []),
        "p_reason":str(reason or ""),
    }
    rows=_data(_retry_db(lambda:
        client().rpc("apply_emergency_rescue_v2585",payload).execute()
    ))
    if isinstance(rows,dict):
        return rows
    return rows[0] if rows else {}


def create_emergency_rescue_log(
    year: int, month: int, source_slot: int, target_slot: int,
    mover: str, rescued_person: str, reason: str = ""
):
    """Record an already-applied ONE-WAY emergency rescue.

    `mover` must be the authenticated resident under the existing swap INSERT RLS.
    This is an audit row only; it is never a bilateral pending swap.
    """
    row={
        "year":int(year),"month":int(month),
        "slot_a":int(source_slot),"slot_b":int(target_slot),
        "person_a":str(mover),"person_b":str(rescued_person),
        "status":"approved","reason":str(reason or ""),
        "created_at":_now(),"responded_at":_now(),
    }
    return _data(client().table("swap_requests").insert(row).execute())


def get_swap_request(request_id: int) -> Optional[dict]:
    rows=_data(_retry_db(lambda:
        client().table("swap_requests").select("*").eq("id",request_id).limit(1).execute()
    ))
    return rows[0] if rows else None


def list_swap_requests(year: int, month: int, person: Optional[str] = None) -> List[dict]:
    rows=_data(_retry_db(lambda:
        client().table("swap_requests")
        .select("*")
        .eq("year",year)
        .eq("month",month)
        .order("id",desc=True)
        .execute()
    ))
    if person:
        rows=[r for r in rows if r.get("person_a")==person or r.get("person_b")==person]
    return rows


def update_swap_request(request_id: int, status: str, reason: str = ""):
    client().table("swap_requests").update({"status":status,"reason":reason,"responded_at":_now()}).eq("id",request_id).execute()


def respond_swap_request_v2578(request_id: int, action: str, reason: str = "") -> dict:
    """Atomic participant response with lost-response reconciliation.

    If the network drops after Postgres commits but before the HTTP response reaches
    Streamlit, re-read the authoritative row. This prevents an indeterminate
    Accept/Reject state after transient RemoteProtocolError failures.
    """
    action=str(action).strip().lower()
    reason=str(reason or "")
    expected_status={"accept":"approved","reject":"rejected","cancel":"rejected"}.get(action)
    try:
        rows=_data(client().rpc("respond_swap_request_v2578",{
            "p_request_id":int(request_id),
            "p_action":action,
            "p_reason":reason,
        }).execute())
        if isinstance(rows,dict):
            return rows
        return rows[0] if rows else {}
    except Exception as exc:
        # Safe reconciliation is useful for any transport/protocol exception. If
        # the server did not commit, the row stays pending and we re-raise.
        try:
            saved=get_swap_request(int(request_id))
        except Exception:
            raise exc
        if saved and expected_status and saved.get("status")==expected_status:
            saved_reason=str(saved.get("reason") or "")
            # Require the reason/meta written by this action when supplied. This
            # avoids mistaking somebody else's prior response for our lost reply.
            if (not reason) or saved_reason==reason:
                saved=dict(saved)
                saved["_reconciled_after_transport_error"]=True
                return saved
        raise


def cancel_swap_request(request_id: int) -> dict:
    return respond_swap_request_v2578(request_id,"cancel","cancelled_by_requester")


def cancel_backup_swap_request(request_id: int):
    client().rpc("cancel_backup_swap_request",{"p_request_id":int(request_id)}).execute()


def sync_backups(year: int, month: int, desired: List[dict]):
    existing={int(r["covered_slot"]):r for r in list_backups(year,month)}
    desired_ids=set()
    for item in desired:
        sid=int(item["covered_slot"]); desired_ids.add(sid); old=existing.get(sid,{})
        row={"year":year,"month":month,"covered_slot":sid,
             "covered_person":str(item.get("covered_person") or ""),
             "covered_block":str(item.get("block") or ""),
             "planned_backup":str(item["planned_backup"]),
             "actual_backup":old.get("actual_backup"),"note":old.get("note","") or "",
             "completed_at":old.get("completed_at"),"completed_by":old.get("completed_by"),"updated_at":_now()}
        client().table("backup_assignments").upsert(row,on_conflict="year,month,covered_slot").execute()
    for sid,r in existing.items():
        if sid not in desired_ids and not r.get("completed_at"):
            client().table("backup_assignments").delete().eq("id",r["id"]).execute()


def list_backup_claims(year: int, month: int) -> List[dict]:
    """All self-selected backup slots for the month."""
    return _data(_retry_db(lambda:
        client().table("weekend_backup_claims")
        .select("*")
        .eq("year",int(year))
        .eq("month",int(month))
        .order("claimed_at")
        .execute()
    ))


def list_weekend_backup_claims(year: int, month: int) -> List[dict]:
    # Compatibility alias used by older code / already deployed DB.
    return list_backup_claims(year,month)


def get_backup_claims(year: int, month: int, initials: str) -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("weekend_backup_claims")
        .select("*")
        .eq("year",int(year))
        .eq("month",int(month))
        .eq("initials",initials)
        .order("claimed_at")
        .execute()
    ))


def get_weekend_backup_claim(year: int, month: int, initials: str) -> Optional[dict]:
    rows=get_backup_claims(year,month,initials)
    return rows[0] if rows else None


def claim_backup_slot(year: int, month: int, initials: str, covered_slot: int):
    """Claim one concrete eligible backup slot.

    Multiple slots per resident are supported. Slot uniqueness is enforced by the DB
    migration so two residents cannot claim the same covered slot concurrently.
    """
    existing=_data(
        client().table("weekend_backup_claims")
        .select("id,initials")
        .eq("year",int(year))
        .eq("month",int(month))
        .eq("covered_slot",int(covered_slot))
        .limit(1)
        .execute()
    )
    if existing:
        if existing[0].get("initials")==initials:
            return
        raise RuntimeError("BACKUP_SLOT_ALREADY_CLAIMED")
    client().table("weekend_backup_claims").insert({
        "year":int(year),"month":int(month),"covered_slot":int(covered_slot),
        "initials":initials,"source":"self","claimed_at":_now(),"updated_at":_now()
    }).execute()


def release_backup_slot(year: int, month: int, initials: str, covered_slot: int):
    client().table("weekend_backup_claims").delete() \
        .eq("year",int(year)).eq("month",int(month)) \
        .eq("initials",initials).eq("covered_slot",int(covered_slot)).execute()


def replace_backup_claims(year: int, month: int, initials: str, covered_slots: List[int]):
    """Replace this resident's full monthly backup-slot selection."""
    covered_slots=sorted({int(x) for x in covered_slots})
    current=get_backup_claims(year,month,initials)
    current_ids={int(r["covered_slot"]) for r in current}
    wanted=set(covered_slots)

    for sid in sorted(current_ids-wanted):
        release_backup_slot(year,month,initials,sid)
    for sid in sorted(wanted-current_ids):
        claim_backup_slot(year,month,initials,sid)


def claim_weekend_backup(year: int, month: int, initials: str, covered_slot: int):
    # Compatibility wrapper: older UI expected one claim and replaced it.
    current=get_backup_claims(year,month,initials)
    for row in current:
        release_backup_slot(year,month,initials,int(row["covered_slot"]))
    claim_backup_slot(year,month,initials,covered_slot)


def release_weekend_backup_claim(year: int, month: int, initials: str):
    client().table("weekend_backup_claims").delete().eq("year",int(year)).eq("month",int(month)).eq("initials",initials).execute()


def create_backup_swap_request(year: int, month: int, requester: str, requester_slot: int, target: str, target_slot: int, note: str=""):
    return _data(client().table("backup_swap_requests").insert({
        "year":int(year),"month":int(month),
        "requester":requester,"requester_slot":int(requester_slot),
        "target":target,"target_slot":int(target_slot),
        "status":"pending","note":note
    }).execute())


def list_backup_swap_requests(year: int, month: int, initials: Optional[str]=None) -> List[dict]:
    def _read():
        q=client().table("backup_swap_requests").select("*").eq("year",int(year)).eq("month",int(month))
        if initials:
            q=q.or_(f"requester.eq.{initials},target.eq.{initials}")
        return q.order("created_at",desc=True).execute()
    return _data(_retry_db(_read))


def reject_backup_swap_request(request_id: int):
    client().table("backup_swap_requests").update({"status":"rejected","responded_at":_now()}).eq("id",int(request_id)).execute()


def accept_backup_swap_request(request_id: int):
    client().rpc("accept_backup_swap",{"p_request_id":int(request_id)}).execute()


def list_backups(year: int, month: int) -> List[dict]:
    return _data(_retry_db(lambda: client().table("backup_assignments").select("*").eq("year",year).eq("month",month).order("covered_slot").execute()))


def set_actual_backup(backup_id: int, actual_backup: Optional[str], note: Optional[str] = None):
    payload={"actual_backup":actual_backup,"updated_at":_now()}
    if note is not None: payload["note"]=note
    client().table("backup_assignments").update(payload).eq("id",backup_id).execute()


def clear_actual_backup(backup_id: int):
    set_actual_backup(backup_id,None)


def set_backup_note(backup_id: int, note: str):
    client().table("backup_assignments").update({"note":str(note or ""),"updated_at":_now()}).eq("id",int(backup_id)).execute()


def activate_backup(backup_id: int):
    client().table("backup_assignments").update({
        "activated_at": _now(),
        "activated_by": auth_user_id(),
        "updated_at": _now(),
    }).eq("id", int(backup_id)).execute()


def clear_backup_activation(backup_id: int):
    client().table("backup_assignments").update({
        "activated_at": None,
        "activated_by": None,
        "updated_at": _now(),
    }).eq("id", int(backup_id)).execute()


def complete_backup_cover(backup_id: int) -> dict:
    """Atomic reciprocal event: coverer earns/settles; covered resident incurs/offsets."""
    rows=_data(client().rpc("complete_backup_cover_v255", {"p_backup_id":int(backup_id)}).execute())
    return rows[0] if rows else {}


def award_backup_credit(backup_id: int, *args, **kwargs) -> dict:
    # Compatibility alias: V2.5.5 derives type from the covered slot.
    return complete_backup_cover(backup_id)


def undo_backup_credit(backup_id: int):
    client().rpc("undo_backup_credit", {"p_backup_id":int(backup_id)}).execute()


def _target_month_start(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}-01T00:00:00+00:00"


def rest_credit_balances(initials: str) -> Dict[str,int]:
    """Currently usable, unexpired, unconsumed and unredeemed rest credits."""
    now_dt=datetime.now(timezone.utc)
    rows=_data(_retry_db(lambda:
        client().table("backup_credit_earnings")
        .select("credit_type,expires_at,redeemed_at,consumed_at")
        .eq("initials",initials).execute()
    ))
    out={"AM":0,"PM":0,"NIGHT":0}
    for r in rows:
        typ=(r.get("credit_type") or "AM").upper()
        if typ not in out or r.get("redeemed_at") or r.get("consumed_at"):
            continue
        exp_dt=_parse_dt(r.get("expires_at"))
        if exp_dt and exp_dt <= now_dt:
            continue
        out[typ]+=1
    return out


def rest_credit_available_for_month(initials: str, year: int, month: int, credit_type: str) -> int:
    """Credits that are valid at the start of target month; includes credits already reserved for that month."""
    typ=credit_type.upper()
    target_dt=_parse_dt(_target_month_start(year,month))
    now_dt=datetime.now(timezone.utc)
    valid_after=max(target_dt,now_dt) if target_dt else now_dt
    rows=_data(_retry_db(lambda:
        client().table("backup_credit_earnings")
        .select("credit_type,expires_at,redeemed_year,redeemed_month,redeemed_at,consumed_at")
        .eq("initials",initials).eq("credit_type",typ).execute()
    ))
    n=0
    for r in rows:
        if r.get("consumed_at"):
            continue
        exp_dt=_parse_dt(r.get("expires_at"))
        if exp_dt and exp_dt < valid_after:
            continue
        ry=r.get("redeemed_year"); rm=r.get("redeemed_month")
        if r.get("redeemed_at") and not (int(ry or 0)==int(year) and int(rm or 0)==int(month)):
            continue
        n+=1
    return n


def all_rest_credit_balances() -> Dict[str,dict]:
    rows=_data(_retry_db(lambda:
        client().table("backup_credit_earnings")
        .select("initials,credit_type,expires_at,redeemed_at,consumed_at").execute()
    ))
    now_dt=datetime.now(timezone.utc); out={}
    for r in rows:
        i=r["initials"]; out.setdefault(i,{"AM":0,"PM":0,"NIGHT":0})
        typ=(r.get("credit_type") or "AM").upper()
        if typ not in out[i] or r.get("redeemed_at") or r.get("consumed_at"):
            continue
        exp_dt=_parse_dt(r.get("expires_at"))
        if exp_dt and exp_dt <= now_dt:
            continue
        out[i][typ]+=1
    return out


def list_open_work_debts(initials: Optional[str] = None) -> List[dict]:
    def _read():
        q=client().table("backup_work_debts").select("*").is_("settled_at","null")
        if initials:
            q=q.eq("initials",initials)
        return q.order("due_at").execute()
    return _data(_retry_db(_read))


def work_debt_balances(initials: str) -> Dict[str,int]:
    out={"AM":0,"PM":0,"NIGHT":0}
    for r in list_open_work_debts(initials):
        typ=(r.get("debt_type") or "").upper()
        if typ in out: out[typ]+=1
    return out


def all_work_debt_balances() -> Dict[str,dict]:
    out={}
    for r in list_open_work_debts():
        i=r["initials"]; out.setdefault(i,{"AM":0,"PM":0,"NIGHT":0})
        typ=(r.get("debt_type") or "").upper()
        if typ in out[i]: out[i][typ]+=1
    return out


def set_rest_credit_redemptions(initials: str, year: int, month: int, am_units: int, pm_units: int):
    client().rpc("set_rest_credit_redemptions_v255", {
        "p_initials":initials,"p_year":int(year),"p_month":int(month),
        "p_am":int(am_units),"p_pm":int(pm_units),
    }).execute()


def redemption_units(initials: str, year: int, month: int, credit_type: str) -> int:
    rows=_data(_retry_db(lambda:
        client().table("backup_credit_redemptions").select("units")
        .eq("initials",initials).eq("target_year",int(year)).eq("target_month",int(month))
        .eq("credit_type",credit_type.upper()).limit(1).execute()
    ))
    return int(rows[0].get("units",0)) if rows else 0


# Compatibility helpers used by older UI code paths.
def credit_balance(initials: str) -> int:
    b=rest_credit_balances(initials)
    return b["AM"]+b["PM"]+b["NIGHT"]


def all_credit_balances() -> Dict[str,int]:
    typed=all_rest_credit_balances()
    return {i:sum(b.values()) for i,b in typed.items()}


def credit_balance_for_month(initials: str, year: int, month: int) -> int:
    return rest_credit_available_for_month(initials,year,month,"AM") + rest_credit_available_for_month(initials,year,month,"PM")


def redeem_credits(initials: str, year: int, month: int, units: int):
    # Legacy no-op-compatible splitter: V2.5.5 publication uses set_rest_credit_redemptions directly.
    set_rest_credit_redemptions(initials,year,month,int(units),0)



def published_baselines_before(year: int, month: int) -> List[dict]:
    """Published SYSTEM schedules strictly before the requested month."""
    rows=_data(_retry_db(lambda:
        client().table("schedules").select(
            "year,month,baseline_json,status"
        ).eq("status","published").execute()
    ))
    target=int(year)*12+int(month)
    out=[]
    for r in rows:
        if int(r.get("year",0))*12+int(r.get("month",0)) < target and r.get("baseline_json"):
            out.append(r)
    return sorted(out,key=lambda r:(int(r["year"]),int(r["month"])))

def fairness_cumulative_before(year: int, month: int) -> Dict[str,dict]:
    """Sum finalized monthly fairness burdens strictly before target month."""
    rows=_data(_retry_db(lambda:
        client().table("fairness_history").select(
            "year,month,initials,weekend_assignments,friday_assignments,doubles,weekday_days"
        ).execute()
    ))
    target_key=int(year)*12+int(month)
    out={}
    for r in rows:
        if int(r["year"])*12+int(r["month"]) >= target_key:
            continue
        i=r["initials"]
        b=out.setdefault(i,{"weekend":0,"friday":0,"double":0,"weekday_day":0})
        b["weekend"]+=int(r.get("weekend_assignments",0))
        b["friday"]+=int(r.get("friday_assignments",0))
        b["double"]+=int(r.get("doubles",0))
        b["weekday_day"]+=int(r.get("weekday_days",0))
    return out


def sync_fairness_history(year: int, month: int, people_stats: Dict[str,dict]):
    """Freeze the published SYSTEM fairness burden for future cumulative balancing.

    V2.5.52: weekend exposure is critical educational/fatigue load, so ALL worked
    weekend assignments (including voluntarily preferred dates) enter the weekend
    history. Fridays retain the legacy voluntary-neutral burden treatment.
    """
    rows=[]
    for initials,d in people_stats.items():
        rows.append({
            "year":int(year),"month":int(month),"initials":initials,
            "weekend_assignments":int(d.get("weekend_assignments",0)),
            "friday_assignments":int(d.get("fairness_friday_assignments",d.get("friday_assignments",0))),
            "doubles":int(d.get("doubles",0)),
            "weekday_days":int(d.get("weekday_days",0)),
            "updated_at":_now(),
        })
    if rows:
        client().table("fairness_history").upsert(
            rows,on_conflict="year,month,initials"
        ).execute()


def fairness_history_rows(up_to_year: Optional[int] = None, up_to_month: Optional[int] = None) -> List[dict]:
    rows=_data(_retry_db(lambda:
        client().table("fairness_history").select(
            "year,month,initials,weekend_assignments,friday_assignments,doubles,weekday_days,updated_at"
        ).order("year").order("month").order("initials").execute()
    ))
    if up_to_year is not None and up_to_month is not None:
        key=int(up_to_year)*12+int(up_to_month)
        rows=[r for r in rows if int(r["year"])*12+int(r["month"])<=key]
    return rows


def apply_schedule_repair(year: int, month: int, current_payload: dict, slot_id: int, day: int, department: str, block: str, from_person: str, to_person: str, reason: str, note: str = ""):
    client().rpc("apply_schedule_repair_v2512", {
        "p_year":int(year),"p_month":int(month),"p_current_json":current_payload,
        "p_slot_id":int(slot_id),"p_day":int(day),"p_department":department,"p_block":block,
        "p_from_person":from_person,"p_to_person":to_person,"p_reason":reason,"p_note":note or ""
    }).execute()


def list_schedule_repairs(year: int, month: int) -> List[dict]:
    return _data(_retry_db(lambda:
        client().rpc("list_schedule_repairs_v2512", {
            "p_year":int(year),"p_month":int(month)
        }).execute()
    ))


def record_email(initials: str, kind: str, target_year: int, target_month: int, send_date: str, status: str, detail: str = ""):
    row={"initials":initials,"kind":kind,"target_year":target_year,"target_month":target_month,"send_date":send_date,"status":status,"detail":detail,"sent_at":_now()}
    client().table("email_log").upsert(row,on_conflict="initials,kind,target_year,target_month,send_date").execute()


def email_already_recorded(initials: str, kind: str, target_year: int, target_month: int, send_date: str) -> bool:
    rows=_data(client().table("email_log").select("id").eq("initials",initials).eq("kind",kind).eq("target_year",target_year).eq("target_month",target_month).eq("send_date",send_date).limit(1).execute())
    return bool(rows)


def get_email_log(target_year: int, target_month: int, limit: int = 200) -> List[dict]:
    return _data(client().table("email_log").select("*").eq("target_year",target_year).eq("target_month",target_month).order("id",desc=True).limit(limit).execute())


def get_manual(lang: str) -> str:
    rows=_data(client().table("manual_docs").select("content").eq("lang",lang).limit(1).execute())
    return rows[0].get("content","") if rows else _default_manuals.get(lang,"")


def save_manual(lang: str, content: str):
    client().table("manual_docs").upsert({"lang":lang,"content":content,"updated_at":_now()},on_conflict="lang").execute()


# --- V2.5.9 Research survey / dashboard ---
def get_my_research_survey(phase: str, year: int, month: int) -> Optional[dict]:
    rows=_data(client().table("research_survey_responses").select("phase,cycle_year,cycle_month,answers,free_text,submitted_at,updated_at").eq("phase",phase).eq("cycle_year",int(year)).eq("cycle_month",int(month)).limit(1).execute())
    return rows[0] if rows else None


def submit_research_survey(phase: str, year: int, month: int, answers: dict, free_text: dict) -> int:
    data=_data(client().rpc("submit_research_survey",{
        "p_phase":phase,
        "p_cycle_year":int(year),
        "p_cycle_month":int(month),
        "p_answers":answers,
        "p_free_text":free_text,
    }).execute())
    if isinstance(data,list) and data:
        try: return int(data[0])
        except Exception:
            if isinstance(data[0],dict):
                return int(next(iter(data[0].values())))
    try: return int(data)
    except Exception: return 0


def research_survey_summary() -> List[dict]:
    return _data(client().rpc("research_survey_summary",{}).execute())


def research_survey_counts() -> List[dict]:
    return _data(client().rpc("research_survey_counts",{}).execute())


def research_survey_comments() -> List[dict]:
    return _data(client().rpc("research_survey_comments",{}).execute())


def research_survey_deidentified() -> List[dict]:
    return _data(client().rpc("research_survey_deidentified",{}).execute())


# --- V2.5.10 role-specific research study layer ---
def research_checkpoint_counts() -> List[dict]:
    return _data(client().rpc("research_checkpoint_counts",{}).execute())


def research_checkpoint_summary() -> List[dict]:
    return _data(client().rpc("research_checkpoint_summary",{}).execute())


def research_comments_v2510() -> List[dict]:
    return _data(client().rpc("research_comments_v2510",{}).execute())


def get_my_scheduler_research_checkpoint(year: int, month: int, checkpoint: str) -> Optional[dict]:
    rows=_data(client().table("research_scheduler_checkpoints").select("cycle_year,cycle_month,checkpoint,answers,free_text,submitted_at,updated_at").eq("cycle_year",int(year)).eq("cycle_month",int(month)).eq("checkpoint",checkpoint).limit(1).execute())
    return rows[0] if rows else None


def submit_scheduler_research_checkpoint(year: int, month: int, checkpoint: str, answers: dict, free_text: dict) -> int:
    data=_data(client().rpc("submit_scheduler_research_checkpoint",{
        "p_cycle_year":int(year),"p_cycle_month":int(month),"p_checkpoint":checkpoint,
        "p_answers":answers,"p_free_text":free_text,
    }).execute())
    if isinstance(data,list) and data:
        v=data[0]
        if isinstance(v,dict): v=next(iter(v.values()))
        return int(v)
    try: return int(data)
    except Exception: return 0


def research_scheduler_dashboard() -> List[dict]:
    return _data(client().rpc("research_scheduler_dashboard",{}).execute())


def get_my_observer_research_checkpoint(year: int, month: int, checkpoint: str) -> Optional[dict]:
    rows=_data(client().table("research_observer_responses").select("cycle_year,cycle_month,checkpoint,answers,free_text,submitted_at,updated_at").eq("cycle_year",int(year)).eq("cycle_month",int(month)).eq("checkpoint",checkpoint).limit(1).execute())
    return rows[0] if rows else None


def submit_observer_research_checkpoint(year: int, month: int, checkpoint: str, answers: dict, free_text: dict) -> int:
    data=_data(client().rpc("submit_observer_research_checkpoint",{
        "p_cycle_year":int(year),"p_cycle_month":int(month),"p_checkpoint":checkpoint,
        "p_answers":answers,"p_free_text":free_text,
    }).execute())
    if isinstance(data,list) and data:
        v=data[0]
        if isinstance(v,dict): v=next(iter(v.values()))
        return int(v)
    try: return int(data)
    except Exception: return 0


def research_observer_dashboard() -> List[dict]:
    return _data(client().rpc("research_observer_dashboard",{}).execute())


def record_research_generation_event(year: int, month: int, elapsed_seconds: float, success: bool, hard_errors=None, monthly_fairness=None, cumulative_fairness=None, preference_mean=None):
    return _data(client().rpc("record_research_generation_event",{
        "p_cycle_year":int(year),"p_cycle_month":int(month),"p_elapsed_seconds":float(elapsed_seconds),
        "p_success":bool(success),"p_hard_errors":None if hard_errors is None else int(hard_errors),
        "p_monthly_fairness":monthly_fairness,"p_cumulative_fairness":cumulative_fairness,
        "p_preference_mean":preference_mean,
    }).execute())


def research_generation_dashboard() -> List[dict]:
    return _data(client().rpc("research_generation_dashboard",{}).execute())


# ---------------------------------------------------------------------------
# V2.5.34 VERSIONED RULE PROFILE / RESCUE LAYER
# ---------------------------------------------------------------------------
def list_rule_profiles(limit: int = 20) -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("scheduler_rule_profiles")
        .select("*")
        .order("version_no", desc=True)
        .limit(int(limit))
        .execute()
    ))


def get_active_rule_profile() -> Optional[dict]:
    global _ACTIVE_RULE_PROFILE_CACHE
    try:
        rows=_data(_retry_db(lambda:
            client().table("scheduler_rule_profiles")
            .select("*")
            .eq("is_active",True)
            .order("version_no",desc=True)
            .limit(1)
            .execute()
        ))
        row=rows[0] if rows else None
        if row:
            _ACTIVE_RULE_PROFILE_CACHE=dict(row)
        return row
    except Exception as exc:
        # A transient read failure must not crash the entire Streamlit rerun.
        # Reuse only a previously successful row from this process; never invent
        # a DB rule profile silently.
        if _ACTIVE_RULE_PROFILE_CACHE is not None:
            row=dict(_ACTIVE_RULE_PROFILE_CACHE)
            row["_read_fallback"]="memory_cache"
            row["_read_error"]=str(exc)
            return row
        raise


def create_and_activate_rule_profile(name: str, config: dict, note: str = "") -> dict:
    rows=_data(client().rpc(
        "create_and_activate_scheduler_rule_profile_v2534",
        {"p_name":str(name),"p_config":config,"p_note":str(note or "")}
    ).execute())
    return rows[0] if rows else {}


def activate_rule_profile(profile_id: int) -> dict:
    rows=_data(client().rpc(
        "activate_scheduler_rule_profile_v2534",
        {"p_profile_id":int(profile_id)}
    ).execute())
    return rows[0] if rows else {}


# ---------------------------------------------------------------------------
# V2.5.41 RESEARCH RUN LOCK — AVAILABLE GPT + HUMAN vs MY ENGINE TOOL
# ---------------------------------------------------------------------------
def get_research_scheduler_case_v2541(year: int, month: int) -> Optional[dict]:
    rows=_data(_retry_db(lambda:
        client().table("research_scheduler_cases_v2541")
        .select("*")
        .eq("cycle_year",int(year))
        .eq("cycle_month",int(month))
        .limit(1)
        .execute()
    ))
    return rows[0] if rows else None


def list_research_scheduler_runs_v2541(case_id: str) -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("research_scheduler_runs_v2541")
        .select("*")
        .eq("case_id",str(case_id))
        .order("run_no")
        .execute()
    ))


def create_research_scheduler_case_v2541(
    year: int, month: int, input_hash: str, comparator_schedule_hash: str,
    input_snapshot: dict, comparator_assignments: dict, import_warnings: list,
    gpt_human_iterations=None, gpt_human_minutes=None, method_note: str = "",
    app_version: str = "", rule_profile_version: int = 0,
) -> dict:
    rows=_data(client().rpc("create_research_scheduler_case_v2541",{
        "p_cycle_year":int(year),
        "p_cycle_month":int(month),
        "p_input_hash":str(input_hash),
        "p_comparator_schedule_hash":str(comparator_schedule_hash),
        "p_input_snapshot":input_snapshot,
        "p_comparator_assignments":comparator_assignments,
        "p_import_warnings":import_warnings or [],
        "p_gpt_human_iterations":None if gpt_human_iterations in (None,"") else int(gpt_human_iterations),
        "p_gpt_human_minutes":None if gpt_human_minutes in (None,"") else float(gpt_human_minutes),
        "p_method_note":str(method_note or ""),
        "p_app_version":str(app_version or ""),
        "p_rule_profile_version":int(rule_profile_version or 0),
    }).execute())
    return rows[0] if rows else {}


def record_research_scheduler_run_v2541(
    case_id: str, input_hash: str, elapsed_seconds: float, success: bool,
    app_version: str, rule_profile_version: int, metrics: dict, assignments: dict,
    raw_metrics: Optional[dict] = None,
) -> dict:
    rows=_data(client().rpc("record_research_scheduler_run_v2541",{
        "p_case_id":str(case_id),
        "p_input_hash":str(input_hash),
        "p_elapsed_seconds":float(elapsed_seconds),
        "p_success":bool(success),
        "p_app_version":str(app_version or ""),
        "p_rule_profile_version":int(rule_profile_version or 0),
        "p_solver_stage":metrics.get("solve_stage"),
        "p_hard_errors":metrics.get("hard_errors"),
        "p_monthly_fairness":metrics.get("monthly_fairness_score"),
        "p_cumulative_fairness":metrics.get("cumulative_fairness_score"),
        "p_preference_mean":metrics.get("mean_preference_score"),
        "p_monthly_workplace_imbalance":metrics.get("rotation_monthly_imbalance"),
        "p_cumulative_workplace_imbalance":metrics.get("rotation_cumulative_imbalance"),
        "p_mean_distinct_workplaces":metrics.get("mean_distinct_rotations"),
        "p_weekend_spread":metrics.get("weekend_monthly_spread"),
        "p_friday_spread":metrics.get("friday_monthly_spread"),
        "p_double_spread":metrics.get("double_monthly_spread"),
        "p_weekday_day_spread":metrics.get("weekday_day_monthly_spread"),
        "p_gap_count":metrics.get("optional_gap_count"),
        "p_gap_category_spread":metrics.get("optional_gap_category_spread"),
        "p_raw_metrics":raw_metrics if raw_metrics is not None else metrics,
        "p_assignments":{str(k):v for k,v in (assignments or {}).items()},
    }).execute())
    return rows[0] if rows else {}


def update_research_scheduler_process_v2541(
    case_id: str, gpt_human_iterations=None, gpt_human_minutes=None, method_note: str = ""
) -> dict:
    rows=_data(client().rpc("update_research_scheduler_process_v2541",{
        "p_case_id":str(case_id),
        "p_gpt_human_iterations":None if gpt_human_iterations in (None,"") else int(gpt_human_iterations),
        "p_gpt_human_minutes":None if gpt_human_minutes in (None,"") else float(gpt_human_minutes),
        "p_method_note":str(method_note or ""),
    }).execute())
    return rows[0] if rows else {}


def list_research_scheduler_cases_v2541() -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("research_scheduler_cases_v2541")
        .select("*")
        .order("cycle_year")
        .order("cycle_month")
        .execute()
    ))


# ---------------------------------------------------------------------------
# V2.5.42 QUESTIONNAIRE-ASSISTED RESEARCH
# ---------------------------------------------------------------------------
def list_research_scheduler_questionnaires_v2542(case_id: str) -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("research_scheduler_questionnaires_v2542")
        .select("*")
        .eq("case_id",str(case_id))
        .order("respondent_initials")
        .execute()
    ))


def save_research_scheduler_questionnaire_v2542(
    case_id: str, respondent_initials: str, extract: dict, parsed: dict
) -> dict:
    payload={
        "iterations":parsed.get("iterations"),
        "minutes":parsed.get("minutes"),
        "iteration_evidence":parsed.get("iteration_evidence"),
        "time_evidence":parsed.get("time_evidence"),
        "iteration_candidates":parsed.get("iteration_candidates") or [],
        "time_candidates":parsed.get("time_candidates") or [],
    }
    rows=_data(client().rpc("save_research_scheduler_questionnaire_v2542",{
        "p_case_id":str(case_id),
        "p_respondent_initials":str(respondent_initials),
        "p_file_name":str(extract.get("file_name") or "questionnaire"),
        "p_file_hash":str(extract.get("file_hash") or ""),
        "p_mime_type":str(extract.get("mime_type") or ""),
        "p_file_size":int(extract.get("file_size") or 0),
        "p_extracted_text":str(extract.get("text") or ""),
        "p_parsed_iterations":parsed.get("iterations"),
        "p_parsed_minutes":parsed.get("minutes"),
        "p_parser_payload":payload,
    }).execute())
    return rows[0] if rows else {}


# ---------------------------------------------------------------------------
# V2.5.45+ RESEARCH-ONLY SHADOW GENERATOR
# ---------------------------------------------------------------------------
def get_research_shadow_case_v2545(year: int, month: int) -> Optional[dict]:
    rows=_data(_retry_db(lambda:
        client().table("research_shadow_cases_v2545")
        .select("*")
        .eq("cycle_year",int(year))
        .eq("cycle_month",int(month))
        .limit(1)
        .execute()
    ))
    return rows[0] if rows else None


def list_research_shadow_cases_v2545() -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("research_shadow_cases_v2545")
        .select("*")
        .order("cycle_year")
        .order("cycle_month")
        .execute()
    ))


def list_research_shadow_runs_v2545(case_id: str) -> List[dict]:
    return _data(_retry_db(lambda:
        client().table("research_shadow_runs_v2545")
        .select("*")
        .eq("case_id",str(case_id))
        .order("run_no")
        .execute()
    ))


def create_research_shadow_case_v2545(
    year: int, month: int, input_hash: str, input_snapshot: list,
    import_audit: dict, app_version: str, rule_profile_version: int,
) -> dict:
    rows=_data(client().rpc("create_research_shadow_case_v2545",{
        "p_cycle_year":int(year),
        "p_cycle_month":int(month),
        "p_input_hash":str(input_hash),
        "p_input_snapshot":input_snapshot,
        "p_import_audit":import_audit or {},
        "p_app_version":str(app_version or ""),
        "p_rule_profile_version":int(rule_profile_version or 0),
    }).execute())
    return rows[0] if rows else {}


def reset_research_shadow_case_v2546(year: int, month: int, reason: str = "researcher reset") -> dict:
    """Delete the caller's frozen research shadow case/runs for one month.

    This is research-only and never touches operational schedules, backups or fairness history.
    The SECURITY DEFINER RPC keeps an audit tombstone before deleting the active experiment.
    """
    rows=_data(client().rpc("reset_research_shadow_case_v2546",{
        "p_cycle_year":int(year),
        "p_cycle_month":int(month),
        "p_reason":str(reason or "researcher reset"),
    }).execute())
    return rows[0] if rows else {}


def record_research_shadow_run_v2545(
    case_id: str, input_hash: str, elapsed_seconds: float, success: bool,
    app_version: str, rule_profile_version: int, result_stats: dict,
    assignments: dict,
) -> dict:
    g=(result_stats or {}).get("global",{}) if isinstance(result_stats,dict) else {}
    rows=_data(client().rpc("record_research_shadow_run_v2545",{
        "p_case_id":str(case_id),
        "p_input_hash":str(input_hash),
        "p_elapsed_seconds":float(elapsed_seconds),
        "p_success":bool(success),
        "p_app_version":str(app_version or ""),
        "p_rule_profile_version":int(rule_profile_version or 0),
        "p_solver_stage":g.get("solve_stage"),
        "p_hard_errors":g.get("hard_errors"),
        "p_monthly_fairness":g.get("monthly_fairness_score"),
        "p_cumulative_fairness":g.get("cumulative_fairness_score"),
        "p_preference_mean":g.get("mean_preference_score"),
        "p_monthly_workplace_imbalance":g.get("rotation_monthly_imbalance"),
        "p_cumulative_workplace_imbalance":g.get("rotation_cumulative_imbalance"),
        "p_mean_distinct_workplaces":g.get("mean_distinct_rotations"),
        "p_weekend_spread":g.get("weekend_monthly_spread"),
        "p_friday_spread":g.get("friday_monthly_spread"),
        "p_double_spread":g.get("double_monthly_spread"),
        "p_weekday_day_spread":g.get("weekday_day_monthly_spread"),
        "p_gap_count":g.get("optional_gap_count"),
        "p_gap_category_spread":g.get("optional_gap_category_spread"),
        "p_full_stats":result_stats or {},
        "p_assignments":{str(k):v for k,v in (assignments or {}).items()},
    }).execute())
    return rows[0] if rows else {}
