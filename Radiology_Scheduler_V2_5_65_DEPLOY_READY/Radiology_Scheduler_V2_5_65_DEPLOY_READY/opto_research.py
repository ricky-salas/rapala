from __future__ import annotations

"""Isolated OPTO/RAPA/Human research workbench helpers.

This module is deliberately storage-free: uploads are parsed in memory and no
operational SYSTEM/ACTUAL schedule is changed.  An *extension* describes only a
cohort's local scheduling paradigm (people, posts, shift templates and fairness
limits).  The same frozen extension + preferences can then be used to compare
three schedule-producing methods on identical inputs:

    HUMAN Excel  |  RAPA extension engine  |  OPTO Excel
"""

from dataclasses import asdict
from datetime import date, datetime
from io import BytesIO
import calendar
import json
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from extension_core import (
    ExtensionError,
    GeneralSlot,
    compile_slots,
    extension_summary,
    load_extension,
    normalize_extension,
)

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None
try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


# ---------- generic normalization ----------

def _norm(v: Any) -> str:
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _split_people(v: Any) -> List[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [x.strip() for x in re.split(r"[\n,;/|]+", str(v)) if x.strip()]


def _days(v: Any, ndays: int) -> List[int]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return [int(v.day)] if 1 <= int(v.day) <= ndays else []
    out = []
    for token in re.findall(r"(?<!\d)([0-3]?\d)(?!\d)", str(v)):
        d = int(token)
        if 1 <= d <= ndays and d not in out:
            out.append(d)
    return out


def _block(v: Any) -> str:
    s = str(v or "").lower()
    n = _norm(s)
    if "night" in n or "nakt" in n or "20000800" in n or "20008" in n:
        return "NIGHT"
    if "full" in n or "visa" in n or "12h" in n or "08002000" in n or "0820" in n:
        return "FULL"
    if "pm" in n or "popiet" in n or "vak" in n or "1420" in n:
        return "PM"
    if "am" in n or "ryt" in n or "0814" in n or "814" in n:
        return "AM"
    return str(v or "").strip().upper()


def _when(v: Any) -> str:
    n = _norm(v)
    if "weekend" in n or "savaitgal" in n:
        return "weekends"
    if "holiday" in n or "svent" in n:
        return "holidays"
    if "all" in n or "visosdien" in n:
        return "all_days"
    return "weekdays"


# ---------- extension import ----------

def extension_template_xlsx() -> bytes:
    buf = BytesIO()
    people = pd.DataFrame([
        {"initials": "AA", "name": "Vardas Pavardė"},
        {"initials": "BB", "name": "Vardas Pavardė"},
    ])
    shifts = pd.DataFrame([
        {"department": "CENTRO RO", "block": "AM", "count": 2, "when": "weekdays", "workload2": 2, "fairness_category": "CENTRO RO", "from": "2026-10"},
        {"department": "CENTRO RO", "block": "PM", "count": 2, "when": "weekdays", "workload2": 2, "fairness_category": "CENTRO RO", "from": "2026-10"},
        {"department": "SPS RO budėjimas", "block": "FULL", "count": 1, "when": "weekends", "workload2": 4, "fairness_category": "SPS RO", "from": "2026-10"},
    ])
    meta = pd.DataFrame([
        {"field": "extension_id", "value": "lsmu-radiology-r2"},
        {"field": "name", "value": "LSMU radiologija · II kursas"},
        {"field": "max_workdays_rolling7", "value": 6},
    ])
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        meta.to_excel(w, index=False, sheet_name="META")
        people.to_excel(w, index=False, sheet_name="ŽMONĖS")
        shifts.to_excel(w, index=False, sheet_name="PAMAINOS")
    return buf.getvalue()


def _extension_from_excel(raw: bytes, filename: str) -> Tuple[dict, List[str]]:
    warnings: List[str] = []
    book = pd.ExcelFile(BytesIO(raw))
    people_rows = []
    shift_rows = []
    meta: Dict[str, Any] = {}
    for sh in book.sheet_names:
        df = pd.read_excel(book, sheet_name=sh)
        cols = {_norm(c): c for c in df.columns}
        if {"initials", "name"}.issubset(cols):
            for _, r in df.iterrows():
                ini = str(r.get(cols["initials"], "") or "").strip()
                name = str(r.get(cols["name"], "") or "").strip()
                if ini:
                    people_rows.append({"initials": ini, "name": name or ini})
        elif "department" in cols and "block" in cols:
            for _, r in df.iterrows():
                dep = str(r.get(cols["department"], "") or "").strip()
                if not dep:
                    continue
                shift_rows.append({
                    "department": dep,
                    "block": _block(r.get(cols["block"])),
                    "count": int(float(r.get(cols.get("count"), 1) or 1)),
                    "when": _when(r.get(cols.get("when"), "weekdays")),
                    "workload2": int(float(r.get(cols.get("workload2"), 4 if _block(r.get(cols["block"])) in {"FULL","NIGHT"} else 2) or 2)),
                    "fairness_category": str(r.get(cols.get("fairnesscategory"), dep) or dep),
                    "from": str(r.get(cols.get("from"), "") or "").strip() or None,
                    "until": str(r.get(cols.get("until"), "") or "").strip() or None,
                })
        elif "field" in cols and "value" in cols:
            for _, r in df.iterrows():
                key = str(r.get(cols["field"], "") or "").strip()
                if key:
                    meta[key] = r.get(cols["value"])
    if not people_rows:
        raise ExtensionError("Excel extension nerasta ŽMONĖS lentelė su stulpeliais initials ir name.")
    if not shift_rows:
        raise ExtensionError("Excel extension nerasta PAMAINOS lentelė su department ir block.")
    ext = {
        "schema_version": 1,
        "extension_id": str(meta.get("extension_id") or re.sub(r"\W+", "-", filename.lower())).strip("-"),
        "name": str(meta.get("name") or filename),
        "people": people_rows,
        "shift_templates": shift_rows,
        "fairness": {"max_workdays_rolling7": int(float(meta.get("max_workdays_rolling7") or 6))},
        "rules_notes": f"Importuota iš {filename}",
    }
    return load_extension(ext), warnings


def _extract_doc_text(raw: bytes, ext: str) -> Tuple[str, List[List[str]]]:
    tables: List[List[str]] = []
    if ext == ".docx":
        if Document is None:
            raise ExtensionError("python-docx neįdiegtas")
        doc = Document(BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
        for t in doc.tables:
            for row in t.rows:
                tables.append([c.text.strip() for c in row.cells])
        return text, tables
    if ext == ".pdf":
        if PdfReader is None:
            raise ExtensionError("pypdf neįdiegtas")
        reader = PdfReader(BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in reader.pages), []
    raise ExtensionError("Netinkamas dokumento formatas")


def _extension_from_text_document(raw: bytes, filename: str) -> Tuple[dict, List[str]]:
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    text, tables = _extract_doc_text(raw, suffix)
    warnings = ["Word/PDF taisyklės interpretuojamos kaip extension juodraštis; prieš RAPA paleidimą patvirtinkite santrauką."]

    # Explicit table-like lines are preferred: initials | name OR department | block | count | when.
    people = []
    shifts = []
    for row in tables:
        vals = [x.strip() for x in row if x and x.strip()]
        if len(vals) >= 2 and re.fullmatch(r"[A-ZĄČĘĖĮŠŲŪŽ]{1,4}", vals[0].upper()):
            if _norm(vals[0]) not in {"initials", "inic", "inicialai"}:
                people.append({"initials": vals[0].upper(), "name": vals[1]})
        if len(vals) >= 3 and _block(vals[1]) in {"AM","PM","FULL","NIGHT"}:
            try:
                cnt = int(float(vals[2]))
            except Exception:
                continue
            shifts.append({"department": vals[0], "block": _block(vals[1]), "count": cnt,
                           "when": _when(vals[3] if len(vals) > 3 else "weekdays"),
                           "workload2": 4 if _block(vals[1]) in {"FULL","NIGHT"} else 2,
                           "fairness_category": vals[0]})

    # Also accept simple prose/table lines: "POST: CENTRO RO | AM | 4 | weekdays".
    for line in text.splitlines():
        ln = line.strip()
        m = re.match(r"(?i)^\s*(?:person|zmogus|rezidentas)\s*:\s*([^|]+)\|\s*(.+)$", ln)
        if m:
            people.append({"initials": m.group(1).strip(), "name": m.group(2).strip()})
            continue
        m = re.match(r"(?i)^\s*(?:post|postas|pamaina)\s*:\s*([^|]+)\|\s*([^|]+)\|\s*(\d+)\s*(?:\|\s*([^|]+))?", ln)
        if m:
            b = _block(m.group(2))
            shifts.append({"department": m.group(1).strip(), "block": b, "count": int(m.group(3)),
                           "when": _when(m.group(4) or "weekdays"), "workload2": 4 if b in {"FULL","NIGHT"} else 2,
                           "fairness_category": m.group(1).strip()})

    # Helpful fallback for prose that explicitly states cohort size, but never invent names silently.
    if not people:
        m = re.search(r"(?i)(?:rezident(?:u|ų)|zmoniu|žmonių|nariu|narių)\s*(?:skaicius|skaičius)?\s*[:=]?\s*(\d{1,2})", text)
        if m:
            n = int(m.group(1))
            people = [{"initials": f"R{i:02d}", "name": f"Rezidentas {i:02d}"} for i in range(1, n + 1)]
            warnings.append("Dokumente nerasti vardai; sukurti laikini R01… inicialai. Prieš tyrimą pakeiskite tikrais.")

    # Small prose helper for common "X ryte ir Y vakare" wording.
    if not shifts:
        for line in text.splitlines():
            m = re.search(r"(?i)([A-ZĄČĘĖĮŠŲŪŽ0-9 /.-]{3,40}).*?(\d+)\s*(?:ryte|am).*?(\d+)\s*(?:vakare|pm)", line)
            if m:
                dep = m.group(1).strip(" :-")
                shifts.extend([
                    {"department": dep, "block": "AM", "count": int(m.group(2)), "when": "weekdays", "workload2": 2, "fairness_category": dep},
                    {"department": dep, "block": "PM", "count": int(m.group(3)), "when": "weekdays", "workload2": 2, "fairness_category": dep},
                ])
    if len(people) < 2 or not shifts:
        raise ExtensionError(
            "Iš Word/PDF nepavyko patikimai sudaryti pilno extension. Patogiausia taisykles pateikti lentelėmis: "
            "ŽMONĖS (initials, name) ir PAMAINOS (department, block, count, when), arba naudoti Excel extension šabloną."
        )
    ext = {"schema_version": 1, "extension_id": re.sub(r"\W+", "-", filename.lower()).strip("-"),
           "name": filename, "people": people, "shift_templates": shifts,
           "fairness": {"max_workdays_rolling7": 6}, "rules_notes": text[:10000]}
    return load_extension(ext), warnings


def parse_extension_upload(raw: bytes, filename: str) -> Tuple[dict, List[str]]:
    low = filename.lower()
    if low.endswith(".json"):
        return load_extension(raw), []
    if low.endswith((".xlsx", ".xls")):
        return _extension_from_excel(raw, filename)
    if low.endswith((".docx", ".pdf")):
        return _extension_from_text_document(raw, filename)
    raise ExtensionError("Extension formatas turi būti JSON, Excel, Word arba PDF.")


# ---------- preference import ----------

def preferences_template_xlsx(extension: dict, year: int, month: int) -> bytes:
    ext = normalize_extension(extension)
    rows = []
    for p in ext["people"]:
        rows.append({"initials": p["initials"], "name": p.get("name", ""), "negaliu_dirbti": "", "pageidauju_dirbti": ""})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name="PAGEIDAVIMAI")
    return buf.getvalue()


def parse_preferences_excel(raw: bytes, extension: dict, year: int, month: int) -> Tuple[dict, List[str]]:
    ext = normalize_extension(extension)
    ndays = calendar.monthrange(year, month)[1]
    known = {str(p["initials"]).casefold(): str(p["initials"]) for p in ext["people"]}
    prefs = {str(p["initials"]): {"unavailable_days": [], "preferred_days": []} for p in ext["people"]}
    warnings: List[str] = []
    book = pd.ExcelFile(BytesIO(raw))
    found = 0
    for sh in book.sheet_names:
        df = pd.read_excel(book, sheet_name=sh)
        cols = {_norm(c): c for c in df.columns}
        ini_col = next((cols[k] for k in ("initials","inic","inicialai","zmogus","rezidentas") if k in cols), None)
        if not ini_col:
            continue
        off_col = next((cols[k] for k in ("negaliudirbti","unavailable","hardoff","negaliu") if k in cols), None)
        pref_col = next((cols[k] for k in ("pageidaujudirbti","preferred","noriudirbti") if k in cols), None)
        if not off_col and not pref_col:
            continue
        found += 1
        for _, r in df.iterrows():
            raw_ini = str(r.get(ini_col, "") or "").strip()
            ini = known.get(raw_ini.casefold())
            if not ini:
                if raw_ini:
                    warnings.append(f"{sh}: nežinomas rezidentas '{raw_ini}'")
                continue
            if off_col:
                prefs[ini]["unavailable_days"] = sorted(set(prefs[ini]["unavailable_days"]) | set(_days(r.get(off_col), ndays)))
            if pref_col:
                prefs[ini]["preferred_days"] = sorted(set(prefs[ini]["preferred_days"]) | set(_days(r.get(pref_col), ndays)))
    if not found:
        raise ValueError("Pageidavimų Excel nerasta lentelė su initials + Negaliu dirbti/Pageidauju dirbti.")
    return prefs, warnings


def apply_preferences(extension: dict, preferences: dict) -> dict:
    ext = normalize_extension(extension)
    ext = json.loads(json.dumps(ext, ensure_ascii=False))
    for p in ext["people"]:
        rec = preferences.get(str(p["initials"]), {})
        p["unavailable_days"] = [int(x) for x in rec.get("unavailable_days", [])]
        p["preferred_days"] = [int(x) for x in rec.get("preferred_days", [])]
    return ext


# ---------- schedule Excel import/export ----------

def schedule_template_xlsx(extension: dict, year: int, month: int) -> bytes:
    slots = compile_slots(extension, year, month)
    rows = [{"slot_id": s.idx, "date": f"{year:04d}-{month:02d}-{s.day:02d}", "department": s.department,
             "shift": s.block, "person": ""} for s in slots]
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name="GRAFIKAS")
    return buf.getvalue()


def _dept_match_key(v: Any) -> str:
    n = _norm(v)
    return re.sub(r"\d+$", "", n)


def parse_schedule_excel(raw: bytes, extension: dict, year: int, month: int) -> Tuple[dict, List[str]]:
    ext = normalize_extension(extension)
    slots = compile_slots(ext, year, month)
    slot_by_id = {int(s.idx): s for s in slots}
    people = {str(p["initials"]).casefold(): str(p["initials"]) for p in ext["people"]}
    names = {_norm(p.get("name")): str(p["initials"]) for p in ext["people"] if p.get("name")}
    warnings: List[str] = []
    assignments: Dict[str, str] = {}
    book = pd.ExcelFile(BytesIO(raw))

    # First try tidy tables.
    for sh in book.sheet_names:
        df = pd.read_excel(book, sheet_name=sh)
        cols = {_norm(c): c for c in df.columns}
        person_col = next((cols[k] for k in ("person","zmogus","rezidentas","initials","inic") if k in cols), None)
        if not person_col:
            continue
        slot_col = cols.get("slotid") or cols.get("id")
        date_col = cols.get("date") or cols.get("data") or cols.get("day") or cols.get("diena")
        dep_col = next((cols[k] for k in ("department","skyrius","vieta","padalinys") if k in cols), None)
        shift_col = next((cols[k] for k in ("shift","pamaina","block","laikas") if k in cols), None)
        if not slot_col and not (date_col and dep_col and shift_col):
            continue
        for ridx, r in df.iterrows():
            who = str(r.get(person_col, "") or "").strip()
            if not who:
                continue
            ini = people.get(who.casefold()) or names.get(_norm(who))
            if not ini:
                warnings.append(f"{sh} eil. {int(ridx)+2}: nežinomas žmogus '{who}'")
                continue
            sid = None
            if slot_col:
                try:
                    cand = int(float(r.get(slot_col)))
                    if cand in slot_by_id:
                        sid = cand
                except Exception:
                    pass
            if sid is None:
                dayvals = _days(r.get(date_col), calendar.monthrange(year, month)[1])
                if not dayvals:
                    continue
                day = dayvals[0]
                depk = _dept_match_key(r.get(dep_col))
                block = _block(r.get(shift_col))
                cands = [s for s in slots if s.day == day and s.block == block and _dept_match_key(s.department) == depk]
                unused = [s for s in cands if str(s.idx) not in assignments]
                if not unused:
                    warnings.append(f"{sh} eil. {int(ridx)+2}: nerasta laisva pamaina {day} d. {r.get(dep_col)} {block}")
                    continue
                sid = sorted(unused, key=lambda s: s.idx)[0].idx
            if str(sid) in assignments and assignments[str(sid)] != ini:
                raise ValueError(f"Tas pats slot_id {sid} priskirtas keliems žmonėms")
            assignments[str(sid)] = ini
    if assignments:
        return assignments, warnings

    # Fallback: classic matrix, with calendar days across columns and department rows.
    for sh in book.sheet_names:
        rawdf = pd.read_excel(book, sheet_name=sh, header=None)
        best = None
        for hr in range(min(60, len(rawdf))):
            day_cols = []
            for ci, v in enumerate(rawdf.iloc[hr].tolist()):
                ds = _days(v, calendar.monthrange(year, month)[1])
                if len(ds) == 1:
                    day_cols.append((ci, ds[0]))
            if len({d for _, d in day_cols}) < 3:
                continue
            rows = []
            for ri in range(hr + 1, len(rawdf)):
                desc = " | ".join(str(x) for x in rawdf.iloc[ri, : max(1, min([c for c, _ in day_cols] or [1]))].tolist() if str(x) != "nan")
                depkey = _dept_match_key(desc)
                matches = [s for s in slots if depkey and (_dept_match_key(s.department) in depkey or depkey in _dept_match_key(s.department))]
                if matches:
                    rows.append((ri, matches, desc))
            score = len(day_cols) + 2 * len(rows)
            if rows and (best is None or score > best[0]):
                best = (score, hr, day_cols, rows)
        if not best:
            continue
        _, hr, day_cols, rows = best
        local_used = set()
        for ri, matches, desc in rows:
            explicit = _block(desc)
            if explicit not in {"AM","PM","FULL","NIGHT"}:
                explicit = None
            for ci, day in day_cols:
                if ci >= rawdf.shape[1]:
                    continue
                vals = _split_people(rawdf.iloc[ri, ci])
                for who in vals:
                    ini = people.get(who.casefold()) or names.get(_norm(who))
                    if not ini:
                        warnings.append(f"{sh}: {day} d. nežinomas žmogus '{who}'")
                        continue
                    cands = [s for s in slots if s.day == day and s.idx not in local_used and s in matches and (explicit is None or s.block == explicit)]
                    if not cands:
                        warnings.append(f"{sh}: {day} d. nerasta laisva pamaina eilutei '{desc}'")
                        continue
                    s = sorted(cands, key=lambda x: x.idx)[0]
                    assignments[str(s.idx)] = ini
                    local_used.add(s.idx)
        if assignments:
            return assignments, warnings
    raise ValueError("Grafiko Excel nepavyko atpažinti. Naudokite tidy formatą arba atsisiųskite šabloną.")


def assignments_dataframe(extension: dict, year: int, month: int, assignments: dict) -> pd.DataFrame:
    slots = {str(s.idx): s for s in compile_slots(extension, year, month)}
    names = {str(p["initials"]): p.get("name", "") for p in normalize_extension(extension)["people"]}
    rows = []
    for sid, ini in sorted(assignments.items(), key=lambda kv: int(kv[0])):
        s = slots.get(str(sid))
        if not s:
            continue
        rows.append({"slot_id": int(sid), "date": f"{year:04d}-{month:02d}-{s.day:02d}", "department": s.department,
                     "shift": s.block, "initials": ini, "name": names.get(ini, "")})
    return pd.DataFrame(rows)


# ---------- RAPA generic extension solver ----------

def solve_rapa_extension(extension: dict, year: int, month: int, time_limit: float = 25.0) -> dict:
    """Generic extension solver preserving RAPA ordering: coverage/safety -> wishes -> fairness."""
    ext = normalize_extension(extension)
    people = ext["people"]
    slots = compile_slots(ext, year, month)
    P, S = len(people), len(slots)
    if P < 2 or S == 0:
        raise ExtensionError("Extension neturi pakankamai žmonių arba pamainų")
    pidx = {str(p["initials"]): i for i, p in enumerate(people)}
    n_x = P * S

    # Additional variables: workload absolute deviations from mean proxy, weekend deviations, post deviations.
    cats = sorted({s.fairness_category for s in slots})
    # Variables are only x; fairness is encoded by weighted assignment cost plus hard corridors.
    c = np.zeros(n_x, dtype=float)
    total_w2 = sum(s.workload2 for s in slots)
    avg_w2 = total_w2 / P
    weekend_total = sum(1 for s in slots if s.weekday >= 5)
    weekend_avg = weekend_total / P
    cat_totals = {cat: sum(1 for s in slots if s.fairness_category == cat) for cat in cats}

    # Tiny deterministic tie-breaking plus positive wish bonus.
    for pi, p in enumerate(people):
        preferred = {int(x) for x in (p.get("preferred_days") or [])}
        for si, s in enumerate(slots):
            idx = pi * S + si
            c[idx] = (pi + 1) * 1e-5 + (si + 1) * 1e-7
            if s.day in preferred:
                c[idx] -= 1.0

    rows = []
    lb = []
    ub = []

    # Coverage exactly one.
    for si in range(S):
        row = {pi * S + si: 1.0 for pi in range(P)}
        rows.append(row); lb.append(1.0); ub.append(1.0)

    # Hard unavailability and overlap/day safety.
    for pi, p in enumerate(people):
        unavailable = {int(x) for x in (p.get("unavailable_days") or [])}
        for si, s in enumerate(slots):
            if s.day in unavailable:
                rows.append({pi * S + si: 1.0}); lb.append(0.0); ub.append(0.0)
        for d in range(1, calendar.monthrange(year, month)[1] + 1):
            inds = [pi * S + si for si, s in enumerate(slots) if s.day == d]
            if inds:
                # At most two 6h shifts; FULL/NIGHT force exclusivity via pairwise constraints below.
                rows.append({i: 1.0 for i in inds}); lb.append(0.0); ub.append(2.0)
            for si, a in enumerate(slots):
                if a.day != d:
                    continue
                for sj in range(si + 1, S):
                    b = slots[sj]
                    if b.day != d:
                        continue
                    incompatible = (a.block in {"FULL","NIGHT"} or b.block in {"FULL","NIGHT"} or a.block == b.block)
                    if incompatible:
                        rows.append({pi * S + si: 1.0, pi * S + sj: 1.0}); lb.append(0.0); ub.append(1.0)
        # NIGHT recovery: no daytime next day.
        for si, s in enumerate(slots):
            if s.block != "NIGHT":
                continue
            for sj, t in enumerate(slots):
                if t.day == s.day + 1 and t.block != "NIGHT":
                    rows.append({pi * S + si: 1.0, pi * S + sj: 1.0}); lb.append(0.0); ub.append(1.0)

    # Workload water-fill corridor, unless explicit target_workload2 exists.
    step = 0
    for s in slots:
        step = math.gcd(step, int(s.workload2))
    step = max(1, step)
    lo = int(math.floor(avg_w2 / step) * step)
    hi = int(math.ceil(avg_w2 / step) * step)
    for pi, p in enumerate(people):
        row = {pi * S + si: float(s.workload2) for si, s in enumerate(slots)}
        if p.get("target_workload2") is not None:
            target = int(p["target_workload2"])
            rows.append(row); lb.append(target); ub.append(target)
        else:
            rows.append(row); lb.append(lo); ub.append(hi)

    # Weekend water-fill 0-1 whenever arithmetic permits.
    we_lo, we_hi = math.floor(weekend_avg), math.ceil(weekend_avg)
    for pi in range(P):
        row = {pi * S + si: 1.0 for si, s in enumerate(slots) if s.weekday >= 5}
        rows.append(row); lb.append(we_lo); ub.append(we_hi)

    # Per-post water-fill 0-1 where feasible by arithmetic. If too tight MILP may fail;
    # retry below without post corridors but preserve hard safety + workload/weekends.
    post_rows_start = len(rows)
    for cat in cats:
        clo, chi = math.floor(cat_totals[cat] / P), math.ceil(cat_totals[cat] / P)
        for pi in range(P):
            row = {pi * S + si: 1.0 for si, s in enumerate(slots) if s.fairness_category == cat}
            rows.append(row); lb.append(clo); ub.append(chi)

    def solve_with_rows(rows_use, lb_use, ub_use):
        rr=[]; cc=[]; vv=[]
        for ri, row in enumerate(rows_use):
            for ci, val in row.items(): rr.append(ri); cc.append(ci); vv.append(val)
        A = csr_matrix((vv, (rr, cc)), shape=(len(rows_use), n_x))
        return milp(c=c, integrality=np.ones(n_x), bounds=Bounds(np.zeros(n_x), np.ones(n_x)),
                    constraints=LinearConstraint(A, np.array(lb_use), np.array(ub_use)),
                    options={"time_limit": float(time_limit), "presolve": True})

    res = solve_with_rows(rows, lb, ub)
    relaxed_posts = False
    if not getattr(res, "success", False):
        relaxed_posts = True
        res = solve_with_rows(rows[:post_rows_start], lb[:post_rows_start], ub[:post_rows_start])
    if not getattr(res, "success", False):
        return {"ok": False, "message": f"RAPA extension solver nerado sprendinio: {getattr(res, 'message', '')}", "assignments": {}, "slots": [asdict(s) for s in slots]}
    x = np.rint(res.x[:n_x]).astype(int).reshape(P, S)
    assignments = {}
    for si, s in enumerate(slots):
        owners = np.where(x[:, si] > 0)[0]
        if len(owners):
            assignments[str(s.idx)] = str(people[int(owners[0])]["initials"])
    return {"ok": True, "message": "Izoliuotas RAPA extension grafikas sugeneruotas.", "assignments": assignments,
            "slots": [asdict(s) for s in slots], "preview_engine": "RAPA_EXTENSION_MILP_V1",
            "post_corridors_relaxed": relaxed_posts}


# ---------- common validation / comparison ----------

def evaluate_schedule(extension: dict, year: int, month: int, assignments: dict) -> dict:
    ext = normalize_extension(extension)
    slots = compile_slots(ext, year, month)
    slot_by_id = {str(s.idx): s for s in slots}
    people = [str(p["initials"]) for p in ext["people"]]
    pmeta = {str(p["initials"]): p for p in ext["people"]}
    workload2 = {p: 0 for p in people}
    weekends = {p: 0 for p in people}
    posts = {p: {} for p in people}
    days = {p: {} for p in people}
    preferred_total = preferred_met = unavailable_violations = 0
    unknown_assignments = 0

    covered = 0
    for sid, who in assignments.items():
        s = slot_by_id.get(str(sid))
        if not s or who not in pmeta:
            unknown_assignments += 1
            continue
        covered += 1
        workload2[who] += int(s.workload2)
        if s.weekday >= 5:
            weekends[who] += 1
        posts[who][s.fairness_category] = posts[who].get(s.fairness_category, 0) + 1
        days[who].setdefault(s.day, []).append(s.block)
        if s.day in {int(x) for x in (pmeta[who].get("unavailable_days") or [])}:
            unavailable_violations += 1

    # Count each resident-day positive wish once.
    for who, p in pmeta.items():
        for d in {int(x) for x in (p.get("preferred_days") or [])}:
            preferred_total += 1
            if days[who].get(d):
                preferred_met += 1

    overlap_violations = 0
    night_recovery_violations = 0
    for who in people:
        for d, blocks in days[who].items():
            if len(blocks) > 2 or any(b in {"FULL","NIGHT"} for b in blocks) and len(blocks) > 1 or len(blocks) != len(set(blocks)):
                overlap_violations += 1
            if "NIGHT" in blocks and days[who].get(d + 1):
                night_recovery_violations += 1

    wlvals = list(workload2.values())
    wevals = list(weekends.values())
    cats = sorted({s.fairness_category for s in slots})
    post_spreads = {}
    for cat in cats:
        vals = [posts[p].get(cat, 0) for p in people]
        post_spreads[cat] = max(vals) - min(vals) if vals else 0
    hard_errors = unavailable_violations + overlap_violations + night_recovery_violations + max(0, len(slots) - covered) + unknown_assignments
    return {
        "coverage_pct": round(100.0 * covered / len(slots), 1) if slots else 100.0,
        "unfilled_slots": max(0, len(slots) - covered),
        "hard_errors": int(hard_errors),
        "unavailable_violations": int(unavailable_violations),
        "overlap_violations": int(overlap_violations),
        "night_recovery_violations": int(night_recovery_violations),
        "wish_pct": round(100.0 * preferred_met / preferred_total, 1) if preferred_total else 100.0,
        "preferred_total": int(preferred_total),
        "preferred_met": int(preferred_met),
        "workload_spread": round((max(wlvals) - min(wlvals)) / 2.0, 2) if wlvals else 0.0,
        "weekend_spread": int(max(wevals) - min(wevals)) if wevals else 0,
        "post_spread_sum": int(sum(post_spreads.values())),
        "post_spread_max": int(max(post_spreads.values())) if post_spreads else 0,
        "post_spreads": post_spreads,
        "covered_slots": int(covered),
        "total_slots": int(len(slots)),
    }


def comparison_dataframe(metrics_by_method: Dict[str, dict]) -> pd.DataFrame:
    labels = [
        ("Padengimas, %", "coverage_pct"),
        ("Neužpildytos pamainos", "unfilled_slots"),
        ("Privalomų taisyklių klaidos", "hard_errors"),
        ("„Dirbti negaliu“ pažeidimai", "unavailable_violations"),
        ("Realių pageidavimų išpildymas, %", "wish_pct"),
        ("Darbo krūvio skirtumas", "workload_spread"),
        ("Savaitgalių skirtumas", "weekend_spread"),
        ("Didžiausias vieno posto skirtumas", "post_spread_max"),
        ("Visų postų netolygumas Σ", "post_spread_sum"),
    ]
    rows = []
    for label, key in labels:
        row = {"Rodiklis": label}
        for method, m in metrics_by_method.items():
            row[method] = m.get(key)
        rows.append(row)
    return pd.DataFrame(rows)


def comparison_xlsx(extension: dict, year: int, month: int, schedules: Dict[str, dict], metrics: Dict[str, dict]) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        comparison_dataframe(metrics).to_excel(w, index=False, sheet_name="PALYGINIMAS")
        pd.DataFrame([extension_summary(extension, year, month)]).to_excel(w, index=False, sheet_name="EXTENSION")
        for method, a in schedules.items():
            assignments_dataframe(extension, year, month, a).to_excel(w, index=False, sheet_name=(method[:28] + "_GRAFIKAS"))
            ps = metrics[method].get("post_spreads", {})
            pd.DataFrame([{"postas": k, "skirtumas": v} for k, v in ps.items()]).to_excel(w, index=False, sheet_name=(method[:24] + "_POSTAI"))
    return buf.getvalue()
