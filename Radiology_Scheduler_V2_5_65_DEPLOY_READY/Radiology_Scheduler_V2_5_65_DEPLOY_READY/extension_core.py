from __future__ import annotations

"""RAPA generic extension core.

This module intentionally sits *beside* the operational cohort engine.  It lets a
new resident group describe itself with a small JSON extension instead of copying
or editing solver code.  The operational fairness engine remains untouched; this
module provides a safe, isolated preview compiler/solver for new groups and a
routing point for future promotion into the production engine.
"""

from dataclasses import dataclass
from datetime import date
import calendar
import json
import math
from typing import Any, Dict, List, Tuple

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

EXTENSION_SCHEMA_VERSION = 1
ALLOWED_BLOCKS = {"AM", "PM", "FULL", "NIGHT"}
ALLOWED_WHEN = {"weekdays", "weekends", "all_days", "weekday_holidays", "holidays"}


@dataclass(frozen=True)
class GeneralSlot:
    idx: int
    day: int
    weekday: int
    department: str
    block: str
    workload2: int
    fairness_category: str


class ExtensionError(ValueError):
    pass


def _month_key(y: int, m: int) -> int:
    return int(y) * 100 + int(m)


def _enabled_for_month(row: dict, year: int, month: int) -> bool:
    key = _month_key(year, month)
    if row.get("from"):
        y, m = [int(x) for x in str(row["from"]).split("-")[:2]]
        if key < _month_key(y, m):
            return False
    if row.get("until"):
        y, m = [int(x) for x in str(row["until"]).split("-")[:2]]
        if key > _month_key(y, m):
            return False
    return bool(row.get("enabled", True))


def validate_extension(ext: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    if not isinstance(ext, dict):
        return {}, ["Extension turi būti JSON objektas."]
    out = dict(ext)
    if int(out.get("schema_version", 0) or 0) != EXTENSION_SCHEMA_VERSION:
        errors.append(f"schema_version turi būti {EXTENSION_SCHEMA_VERSION}")
    if not str(out.get("extension_id") or "").strip():
        errors.append("Trūksta extension_id")
    people = out.get("people") or []
    if not isinstance(people, list) or len(people) < 2:
        errors.append("people turi turėti bent 2 narius")
    initials = []
    for i, p in enumerate(people):
        if not isinstance(p, dict):
            errors.append(f"people[{i}] netinkamas")
            continue
        ini = str(p.get("initials") or "").strip()
        if not ini:
            errors.append(f"people[{i}] trūksta initials")
        initials.append(ini)
    if len(set(initials)) != len(initials):
        errors.append("Žmonių initials turi būti unikalūs")
    templates = out.get("shift_templates") or []
    if not isinstance(templates, list) or not templates:
        errors.append("Trūksta shift_templates")
    for i, t in enumerate(templates):
        if not isinstance(t, dict):
            errors.append(f"shift_templates[{i}] netinkamas")
            continue
        if not str(t.get("department") or "").strip():
            errors.append(f"shift_templates[{i}] trūksta department")
        block = str(t.get("block") or "").upper()
        if block not in ALLOWED_BLOCKS:
            errors.append(f"shift_templates[{i}] block turi būti AM/PM/FULL/NIGHT")
        when = str(t.get("when") or "weekdays")
        if when not in ALLOWED_WHEN:
            errors.append(f"shift_templates[{i}] when netinkamas")
        try:
            if int(t.get("count", 1)) < 0:
                raise ValueError
        except Exception:
            errors.append(f"shift_templates[{i}] count turi būti >=0")
    return out, errors


def load_extension(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    ext, errors = validate_extension(raw)
    if errors:
        raise ExtensionError("; ".join(errors))
    return ext


def normalize_extension(ext: Dict[str, Any]) -> Dict[str, Any]:
    ext = load_extension(ext)
    out = dict(ext)
    out.setdefault("name", out["extension_id"])
    out.setdefault("rules_notes", "")
    out.setdefault("fairness", {})
    out["fairness"].setdefault("weekend_spread_target", 1)
    out["fairness"].setdefault("workload_spread_target2", 2)
    out["fairness"].setdefault("post_spread_target", 1)
    out["fairness"].setdefault("max_workdays_rolling7", 6)
    return out


def _is_holiday(year: int, month: int, day: int, extension: dict) -> bool:
    # General engine accepts explicit holiday dates so it is not country-locked.
    key = f"{year:04d}-{month:02d}-{day:02d}"
    return key in set(extension.get("holidays") or [])


def compile_slots(extension: Dict[str, Any], year: int, month: int) -> List[GeneralSlot]:
    ext = normalize_extension(extension)
    _, ndays = calendar.monthrange(year, month)
    slots: List[GeneralSlot] = []
    idx = 0
    for d in range(1, ndays + 1):
        wd = date(year, month, d).weekday()
        holiday = _is_holiday(year, month, d, ext)
        for t in ext["shift_templates"]:
            if not _enabled_for_month(t, year, month):
                continue
            when = str(t.get("when") or "weekdays")
            active = (
                (when == "weekdays" and wd < 5 and not holiday)
                or (when == "weekends" and wd >= 5)
                or (when == "all_days")
                or (when == "weekday_holidays" and wd < 5 and holiday)
                or (when == "holidays" and holiday)
            )
            if not active:
                continue
            if "weekdays" in t and wd not in {int(x) for x in (t.get("weekdays") or [])}:
                continue
            block = str(t["block"]).upper()
            default_w2 = 4 if block in ("FULL", "NIGHT") else 2
            w2 = int(t.get("workload2", default_w2))
            count = int(t.get("count", 1))
            cat = str(t.get("fairness_category") or t["department"])
            for k in range(count):
                name = str(t["department"])
                if count > 1 and bool(t.get("number_rows", True)):
                    name = f"{name} {k+1}"
                slots.append(GeneralSlot(idx, d, wd, name, block, w2, cat))
                idx += 1
    return slots


def extension_summary(extension: Dict[str, Any], year: int, month: int) -> dict:
    ext = normalize_extension(extension)
    slots = compile_slots(ext, year, month)
    by_cat: Dict[str, int] = {}
    by_block: Dict[str, int] = {}
    for s in slots:
        by_cat[s.fairness_category] = by_cat.get(s.fairness_category, 0) + 1
        by_block[s.block] = by_block.get(s.block, 0) + 1
    return {
        "extension_id": ext["extension_id"],
        "name": ext.get("name"),
        "people": len(ext["people"]),
        "slots": len(slots),
        "workload2": sum(s.workload2 for s in slots),
        "by_category": by_cat,
        "by_block": by_block,
    }


def _overlap(a: str, b: str) -> bool:
    a, b = a.upper(), b.upper()
    if a in ("FULL", "NIGHT") or b in ("FULL", "NIGHT"):
        return True
    return a == b


def solve_extension_preview(extension: Dict[str, Any], year: int, month: int, time_limit: float = 20.0) -> dict:
    """Produce a fast isolated schedule preview from an extension.

    The production cohort engine remains authoritative.  This preview deliberately
    uses a deterministic fairness-aware greedy allocator so a newly described group
    can be sanity-checked immediately without risking the operational schedule.
    It follows the same *ordering of concerns*: coverage/safety first, then workload,
    weekend burden, per-post balance, then positive preferences.
    """
    ext = normalize_extension(extension)
    people = list(ext["people"])
    slots = compile_slots(ext, year, month)
    n, ns = len(people), len(slots)
    if n < 2 or ns == 0:
        raise ExtensionError("Extension neturi pakankamai žmonių arba pamainų")

    total_w2 = sum(s.workload2 for s in slots)
    step = 0
    for _s in slots:
        step = math.gcd(step, int(_s.workload2))
    step = max(1, step)
    avg = total_w2 / float(n)
    target_lo = int(math.floor(avg / step) * step)
    target_hi = int(math.ceil(avg / step) * step)

    workload = {str(p["initials"]): 0 for p in people}
    weekends = {str(p["initials"]): 0 for p in people}
    category_counts = {str(p["initials"]): {} for p in people}
    by_person_day = {str(p["initials"]): {} for p in people}
    assignments: Dict[str, str] = {}
    max_days = int(ext.get("fairness", {}).get("max_workdays_rolling7", 6))
    ndays = calendar.monthrange(year, month)[1]

    pmeta = {str(p["initials"]): p for p in people}

    def assigned_blocks(ini: str, day: int) -> List[str]:
        return list(by_person_day[ini].get(day, []))

    def has_work(ini: str, day: int) -> bool:
        return bool(by_person_day[ini].get(day))

    def rolling_days_if_added(ini: str, day: int) -> int:
        best = 0
        for start in range(max(1, day - 6), min(day, ndays - 6) + 1):
            cnt = sum(1 for d in range(start, min(ndays, start + 6) + 1) if has_work(ini, d) or d == day)
            best = max(best, cnt)
        return best

    def eligible(ini: str, sl: GeneralSlot, enforce_target: bool = True) -> bool:
        p = pmeta[ini]
        if sl.day in {int(x) for x in (p.get("unavailable_days") or [])}:
            return False
        existing = assigned_blocks(ini, sl.day)
        if sl.block in ("FULL", "NIGHT") and existing:
            return False
        if sl.block in ("AM", "PM"):
            if any(b in ("FULL", "NIGHT", sl.block) for b in existing):
                return False
        # Overnight recovery: NIGHT cannot be followed by daytime next day, and
        # daytime cannot be placed immediately after a previous NIGHT.
        if sl.block != "NIGHT" and "NIGHT" in assigned_blocks(ini, sl.day - 1):
            return False
        if sl.block == "NIGHT" and assigned_blocks(ini, sl.day + 1):
            return False
        if not has_work(ini, sl.day) and rolling_days_if_added(ini, sl.day) > max_days:
            return False
        explicit_target = p.get("target_workload2")
        cap = int(explicit_target) if explicit_target is not None else target_hi
        if enforce_target and workload[ini] + sl.workload2 > cap:
            return False
        return True

    # FULL/NIGHT first on each date, then AM/PM; high-count categories are mixed by
    # deterministic name/index tie-breaks rather than relying on upload order alone.
    block_order = {"FULL": 0, "NIGHT": 1, "AM": 2, "PM": 3}
    ordered = sorted(slots, key=lambda s: (s.day, block_order.get(s.block, 9), s.fairness_category, s.department, s.idx))

    unfilled = []
    for sl in ordered:
        candidates = []
        for p in people:
            ini = str(p["initials"])
            if not eligible(ini, sl, True):
                continue
            preferred = sl.day in {int(x) for x in (p.get("preferred_days") or [])}
            catc = int(category_counts[ini].get(sl.fairness_category, 0))
            # Lexicographic-style weighted score: workload first, then weekend,
            # then this post, then preference, then stable initials tie-break.
            score = (
                workload[ini] * 1000
                + (weekends[ini] * 150 if sl.weekday >= 5 else 0)
                + catc * 30
                - (80 if preferred else 0)
                + (sum(1 for _ in assigned_blocks(ini, sl.day)) * 4)
            )
            candidates.append((score, ini))
        if not candidates:
            # Preview may temporarily exceed the ideal workload corridor, but never
            # relaxes safety/unavailability. This is reported visibly below.
            for p in people:
                ini = str(p["initials"])
                if eligible(ini, sl, False):
                    preferred = sl.day in {int(x) for x in (p.get("preferred_days") or [])}
                    catc = int(category_counts[ini].get(sl.fairness_category, 0))
                    score = workload[ini] * 1000 + (weekends[ini] * 150 if sl.weekday >= 5 else 0) + catc * 30 - (80 if preferred else 0)
                    candidates.append((score + 100000, ini))
        if not candidates:
            unfilled.append(sl.idx)
            continue
        _, ini = min(candidates, key=lambda x: (x[0], x[1]))
        assignments[str(sl.idx)] = ini
        workload[ini] += sl.workload2
        if sl.weekday >= 5:
            weekends[ini] += 1
        category_counts[ini][sl.fairness_category] = category_counts[ini].get(sl.fairness_category, 0) + 1
        by_person_day[ini].setdefault(sl.day, []).append(sl.block)

    # Small deterministic repair: move an equal slot from the heaviest resident
    # to the lightest resident whenever this strictly narrows workload spread and
    # does not break safety. This keeps the preview close to the production
    # water-fill intuition without turning the extension checker into a second
    # heavyweight MILP engine.
    if not unfilled:
        slot_by_id={str(sl.idx):sl for sl in slots}
        for _ in range(max(1, ns * 2)):
            hi=max(workload, key=lambda k:(workload[k],k))
            lo=min(workload, key=lambda k:(workload[k],k))
            if workload[hi]-workload[lo] <= step:
                break
            moved=False
            for sid,owner in sorted(assignments.items(), key=lambda kv:int(kv[0])):
                if owner != hi:
                    continue
                sl=slot_by_id[sid]
                if workload[hi]-sl.workload2 < target_lo:
                    continue
                if workload[lo]+sl.workload2 > target_hi:
                    continue
                if not eligible(lo, sl, True):
                    continue
                # Reassign and update ledgers.
                assignments[sid]=lo
                workload[hi]-=sl.workload2; workload[lo]+=sl.workload2
                if sl.weekday>=5:
                    weekends[hi]-=1; weekends[lo]+=1
                category_counts[hi][sl.fairness_category]=category_counts[hi].get(sl.fairness_category,0)-1
                category_counts[lo][sl.fairness_category]=category_counts[lo].get(sl.fairness_category,0)+1
                by_person_day[hi][sl.day].remove(sl.block)
                if not by_person_day[hi][sl.day]:
                    by_person_day[hi].pop(sl.day,None)
                by_person_day[lo].setdefault(sl.day,[]).append(sl.block)
                moved=True
                break
            if not moved:
                break

    ok = not unfilled
    wl_values = list(workload.values())
    we_values = list(weekends.values())
    cat_spreads = {}
    for cat in sorted({s.fairness_category for s in slots}):
        vals = [int(category_counts[str(p["initials"])].get(cat, 0)) for p in people]
        cat_spreads[cat] = (max(vals) - min(vals)) if vals else 0

    return {
        "ok": ok,
        "message": (
            "Izoliuotas extension preview sugeneruotas. Operacinio grafiko nekeičia."
            if ok else
            f"Preview dalinai sugeneruotas; neužpildyta {len(unfilled)} pamainų. Reikia patikslinti extension pajėgumą / taisykles."
        ),
        "assignments": assignments,
        "slots": [s.__dict__ for s in slots],
        "workload2": workload,
        "weekends": weekends,
        "workload_spread2": (max(wl_values) - min(wl_values)) if wl_values else 0,
        "weekend_spread": (max(we_values) - min(we_values)) if we_values else 0,
        "post_spreads": cat_spreads,
        "ideal_target_workload2": [target_lo, target_hi],
        "unfilled_slot_ids": unfilled,
        "extension_id": ext["extension_id"],
        "preview_engine": "EXTENSION_GREEDY_V1",
    }

