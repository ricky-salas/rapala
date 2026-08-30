
from __future__ import annotations

ENGINE_API_VERSION = "2.5.112"

from dataclasses import dataclass, field, asdict, replace
from datetime import date, timedelta
import calendar
import math
import hashlib
from typing import Dict, List, Tuple, Optional, Set

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix, csr_matrix


# ---------------------------------------------------------------------------
# V2.5.34 VERSIONED RULE PROFILE / RESCUE LAYER
# Changeable administrative rules live here once and are consumed by the engine.
# The active database profile is normalized through this schema before use.
# ---------------------------------------------------------------------------
DEFAULT_RULE_PROFILE = {
    "deadline_day": 13,
    "target_daily_hours": 7.6,
    "target_shift_hours": 6.0,
    "max_assignments_per_day": 2,
    "max_hours_per_day": 12.0,
    "min_rest_hours": 11.0,
    "max_workdays_rolling7": 6,
    "max_hours_rolling7": 48.0,
    "swap_max_hours_rolling7": 60.0,
    "onko_even_required": True,
    "onko_first_exposure_required": False,
    "weekend_unique_required": True,
    "weekend_max_assignments_per_resident": 1,
    "backup_weekends": False,  # compatibility-only: generic weekend backup scope retired in V2.5.98
    "backup_sps_ro": True,
    "backup_sps_ug": True,
    "backup_centro120_am": True,
    "backup_onko_ro": True,
    "backup_centro_ro_best_effort": True,
    "post_guardrail_tolerance": 0,
    "general_guardrail_tolerance": 1,
    "monthly_post_spread_weight": 1200.0,
    "cumulative_post_catchup_weight": 0.0,
    "active_date_reward": 300.0,
}

_RULE_RANGES = {
    "deadline_day": (1, 28),
    "target_daily_hours": (1.0, 24.0),
    "target_shift_hours": (1.0, 24.0),
    "max_assignments_per_day": (1, 4),
    "max_hours_per_day": (1.0, 24.0),
    "min_rest_hours": (0.0, 24.0),
    "max_workdays_rolling7": (1, 7),
    "max_hours_rolling7": (1.0, 168.0),
    "swap_max_hours_rolling7": (48.0, 60.0),
    "weekend_max_assignments_per_resident": (1, 4),
    "post_guardrail_tolerance": (0, 5),
    "general_guardrail_tolerance": (0, 5),
    "monthly_post_spread_weight": (0.0, 100000.0),
    "cumulative_post_catchup_weight": (0.0, 100000.0),
    "active_date_reward": (0.0, 100000.0),
}

_BOOL_RULES = {
    "onko_even_required",
    "onko_first_exposure_required",
    "weekend_unique_required",
    "backup_weekends",
    "backup_sps_ro",
    "backup_sps_ug",
    "backup_centro120_am",
    "backup_onko_ro",
    "backup_centro_ro_best_effort",
}
_INT_RULES = {
    "deadline_day",
    "max_assignments_per_day",
    "max_workdays_rolling7",
    "weekend_max_assignments_per_resident",
    "post_guardrail_tolerance",
    "general_guardrail_tolerance",
}

_RUNTIME_RULES = dict(DEFAULT_RULE_PROFILE)


def validate_rule_profile(raw: Optional[dict] = None) -> Tuple[dict, List[str]]:
    """Return normalized safe rule profile + validation errors."""
    raw = dict(raw or {})
    unknown = sorted(set(raw) - set(DEFAULT_RULE_PROFILE))
    errors = [f"Unknown rule key: {k}" for k in unknown]
    out = dict(DEFAULT_RULE_PROFILE)
    for key, default in DEFAULT_RULE_PROFILE.items():
        value = raw.get(key, default)
        try:
            if key in _BOOL_RULES:
                if isinstance(value, str):
                    value = value.strip().lower() in ("1","true","yes","on")
                else:
                    value = bool(value)
            elif key in _INT_RULES:
                value = int(value)
            else:
                value = float(value)
        except Exception:
            errors.append(f"{key}: invalid value {value!r}")
            value = default
        if key in _RULE_RANGES and isinstance(value, (int,float)):
            lo, hi = _RULE_RANGES[key]
            if value < lo or value > hi:
                errors.append(f"{key}: must be between {lo} and {hi}")
        out[key] = value

    # V2.5.67 constitution: the calculated monthly workload target is exact HARD.
    # Onko is a 9h / 1.5-unit FULL shift, so odd individual Onko counts would force
    # a half-unit workload deviation. Therefore Onko is allocated in pairs (0,2,4...)
    # and its monthly resident-to-resident spread is capped at 2. The old sparse
    # first-exposure override is kept only as a backwards-compatible profile key
    # and is forcibly disabled here.
    out["onko_first_exposure_required"] = False
    out["onko_even_required"] = True
    # V2.5.98: backup coverage is position-based, never generic weekend-based.
    out["backup_weekends"] = False

    if out["target_shift_hours"] <= 0:
        errors.append("target_shift_hours must be > 0")
    if out["max_hours_per_day"] < 9:
        errors.append("max_hours_per_day cannot be below 9h while FULL 08:00–17:00 shifts exist")
    if out["min_rest_hours"] > 24:
        errors.append("min_rest_hours cannot exceed 24h")
    if out["weekend_unique_required"] and out["weekend_max_assignments_per_resident"] > 1:
        errors.append("weekend_unique_required requires weekend_max_assignments_per_resident = 1")
    if not any(out[k] for k in ("backup_weekends","backup_sps_ro","backup_sps_ug","backup_centro120_am","backup_onko_ro","backup_centro_ro_best_effort")):
        errors.append("At least one backup scope must remain enabled")
    return out, errors


def set_runtime_rules(raw: Optional[dict] = None) -> dict:
    """Install the active validated database profile for this process."""
    global _RUNTIME_RULES
    normalized, errors = validate_rule_profile(raw)
    if errors:
        raise ValueError("Invalid rule profile: " + "; ".join(errors))
    _RUNTIME_RULES = normalized
    return dict(_RUNTIME_RULES)


def get_runtime_rules() -> dict:
    return dict(_RUNTIME_RULES)


def rule_value(key: str):
    return _RUNTIME_RULES.get(key, DEFAULT_RULE_PROFILE[key])


@dataclass
class Person:
    initials: str
    name: str
    unavailable: Set[int] = field(default_factory=set)       # HARD: whole day
    unavailable_am: Set[int] = field(default_factory=set)    # HARD: morning block
    unavailable_pm: Set[int] = field(default_factory=set)    # HARD: afternoon block
    vacation: Set[int] = field(default_factory=set)           # ABSOLUTE HARD: approved vacation / leave
    justified_absence: Set[int] = field(default_factory=set)  # ABSOLUTE HARD: other approved no-work date
    long_duty: Set[int] = field(default_factory=set)          # start date of >12-24h / 24h duty
    reserved_backup: Set[Tuple[int, str]] = field(default_factory=set)  # self-claimed WEEKEND/SPS backup slots
    soft_free: Set[int] = field(default_factory=set)         # SOFT: would like the whole day off
    soft_free_am: Set[int] = field(default_factory=set)      # SOFT: would like morning off
    soft_free_pm: Set[int] = field(default_factory=set)      # SOFT: would like afternoon off
    preferred: Set[int] = field(default_factory=set)         # SOFT: would like to work whole day / any block
    preferred_am: Set[int] = field(default_factory=set)      # SOFT: would like a morning assignment
    preferred_pm: Set[int] = field(default_factory=set)      # SOFT: would like an afternoon assignment
    note: str = ""
    target_adjustment: int = 0
    # Frozen, structured resident-request ledger assembled by the app/import layer.
    # It is carried into the schedule payload so published-vs-ACTUAL satisfaction
    # is always recalculated against the ORIGINAL submitted request set.
    request_items: List[dict] = field(default_factory=list)
    rest_credit_am_to_use: int = 0
    rest_credit_pm_to_use: int = 0

    # SOFT preferences: -2 ... +2 unless noted otherwise
    weekday_preference: int = 0
    weekend_preference: int = 0
    # V2.5.58 dedicated public-holiday inclination: -1 = prefer rest, 0 = neutral, +1 = prefer holiday work.
    # This is a structured SOFT signal used only on official Lithuanian public-holiday duty slots.
    holiday_preference: int = 0
    spread_preference: int = 0   # -2 clustered, +2 dispersed
    # V2.5.70 persistent workday-length preference:
    # 0 = no preference, 1 = prefer 6h singles, 2 = mixed 6h/12h, 3 = prefer 12h AM+PM doubles.
    shift_length_preference: int = 0
    avoid_doubles: bool = False  # legacy compatibility; derived from shift_length_preference==1 in the app

    # Long-term fairness carry-in. These are totals from published prior months.
    prior_weekend_count: int = 0
    prior_holiday_count: int = 0
    prior_friday_count: int = 0
    prior_double_count: int = 0
    prior_weekday_day_count: int = 0
    prior_rotation_counts: Dict[str, int] = field(default_factory=dict)
    # Consecutive weekends worked at the tail of the immediately preceding
    # published SYSTEM month. Used only as a fatigue/spacing tie-breaker.
    prior_consecutive_weekend_streak: int = 0
    # Whether the resident worked Onko RO on the immediately preceding calendar
    # day (the last day of the previous published SYSTEM month). V2.5.68 uses
    # this to enforce the absolute "no Onko on consecutive calendar days" rule
    # across month boundaries as well as inside the month.
    prior_last_day_onko: bool = False
    # Cumulative count of RESIDENT-HARD losses in prior published SYSTEM months.
    prior_resident_hard_loss_count: int = 0


@dataclass(frozen=True)
class Slot:
    idx: int
    day: int
    weekday: int       # Monday = 0
    department: str
    block: str         # AM / PM / FULL
    workload2: int     # workload x2: normal 2, Onko 3
    mandatory: bool
    blocked: bool = False


@dataclass
class SolveResult:
    ok: bool
    message: str
    assignments: Dict[int, str] = field(default_factory=dict)
    targets: Dict[str, int] = field(default_factory=dict)
    stats: Dict[str, dict] = field(default_factory=dict)
    objective_value: Optional[float] = None
    request_snapshot: Optional[dict] = None
    # Planned backup duties frozen at publication. CURRENT/ACTUAL revalidation may
    # override this with the live backup table, while SYSTEM baseline keeps it.
    backup_snapshot: Optional[List[dict]] = None


DEFAULT_PEOPLE = [
    {"initials": "PV", "name": "Pileckienė Aistė", "target_adjustment": 0, "color": "#E76F51"},
    {"initials": "SA", "name": "Sveboda Arminas", "target_adjustment": 0, "color": "#2A9D8F"},
    {"initials": "GD", "name": "Giedrimas Deivydas", "target_adjustment": 0, "color": "#457B9D"},
    {"initials": "GE", "name": "Gertas Ernestas", "target_adjustment": 0, "color": "#F4A261"},
    {"initials": "KE", "name": "Khatskeleva Elena", "target_adjustment": 0, "color": "#8E7DBE"},
    {"initials": "SE", "name": "Stanišauskytė Eglė", "target_adjustment": 0, "color": "#6A994E"},
    {"initials": "MG", "name": "Maleckaitė Gabrielė", "target_adjustment": 0, "color": "#D1495B"},
    {"initials": "MŽ", "name": "Mažonavičius Ignas", "target_adjustment": 0, "color": "#9C6644"},
    {"initials": "GB", "name": "Grumblys Justinas", "target_adjustment": 0, "color": "#3A86FF"},
    {"initials": "SŠ", "name": "Stašinskas Kipras", "target_adjustment": 0, "color": "#8338EC"},
    {"initials": "VL", "name": "Volkovskaja Laura", "target_adjustment": 0, "color": "#D45087"},
    {"initials": "MR", "name": "Montvilaitė Reda", "target_adjustment": 0, "color": "#00A896"},
    {"initials": "SP", "name": "Steponavičiūtė Rosita", "target_adjustment": -2, "color": "#E9C46A"},
    {"initials": "ŠR", "name": "Šalaševičius Rapolas", "target_adjustment": 0, "color": "#43AA8B"},
    {"initials": "DU", "name": "Dulkė Sofija Ana", "target_adjustment": 0, "color": "#577590"},
    {"initials": "SN", "name": "Stankevičiūtė Vytautė", "target_adjustment": 0, "color": "#F9844A"},
]


PERSON_COLORS = {p["initials"]: p["color"] for p in DEFAULT_PEOPLE}


def next_month(today: date) -> Tuple[int, int]:
    if today.month == 12:
        return today.year + 1, 1
    return today.year, today.month + 1


def _easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher), no external dependency."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def lithuanian_public_holidays(year: int) -> Dict[date, str]:
    """Official Lithuanian Labour Code public holidays used by the scheduler.

    Sundays such as Mother's/Father's Day are included as holidays even though they
    are already weekend days; this allows separate holiday-burden/preference audit.
    """
    easter = _easter_sunday(year)
    # First Sunday in May / June.
    may1=date(year,5,1); mother=may1 + timedelta(days=(6-may1.weekday())%7)
    jun1=date(year,6,1); father=jun1 + timedelta(days=(6-jun1.weekday())%7)
    rows={
        date(year,1,1):"Naujieji metai",
        date(year,2,16):"Lietuvos valstybės atkūrimo diena",
        date(year,3,11):"Lietuvos nepriklausomybės atkūrimo diena",
        easter:"Velykų sekmadienis",
        easter+timedelta(days=1):"Velykų pirmadienis",
        date(year,5,1):"Tarptautinė darbo diena",
        mother:"Motinos diena",
        father:"Tėvo diena",
        date(year,6,24):"Rasos ir Joninių diena",
        date(year,7,6):"Valstybės (Lietuvos karaliaus Mindaugo karūnavimo) diena",
        date(year,8,15):"Žolinė",
        date(year,11,1):"Visų Šventųjų diena",
        date(year,11,2):"Vėlinės",
        date(year,12,24):"Kūčios",
        date(year,12,25):"Kalėdos I",
        date(year,12,26):"Kalėdos II",
    }
    return rows


def public_holiday_days_in_month(year: int, month: int) -> Set[int]:
    return {d.day for d in lithuanian_public_holidays(year) if d.month == month}


def is_public_holiday(year: int, month: int, day: int) -> bool:
    return date(year,month,day) in lithuanian_public_holidays(year)


def weekday_count(year: int, month: int) -> int:
    """Normal outpatient working weekdays, excluding statutory public holidays."""
    _, ndays = calendar.monthrange(year, month)
    holidays=public_holiday_days_in_month(year,month)
    return sum(date(year, month, d).weekday() < 5 and d not in holidays for d in range(1, ndays + 1))


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def standard_target(year: int, month: int) -> int:
    return round_half_up(weekday_count(year, month) * float(rule_value("target_daily_hours")) / float(rule_value("target_shift_hours")))


def blocks_overlap(a: str, b: str) -> bool:
    """Whether two schedule blocks overlap in clock time."""
    if a == "FULL" or b == "FULL":
        return True
    return a == b


def resident_hard_unavailable_for_block(person: Person, day: int, block: str) -> bool:
    """Resident-entered `Negaliu dirbti` request.

    V2.5.107 constitution: resident-entered `Negaliu dirbti` is mandatory during
    SYSTEM generation. It is modeled as an assignment prohibition, not as a weighted
    preference or relaxable loss. If coverage/safety/exact workload cannot coexist
    with every such prohibition, generation must fail closed and return no draft.
    Post-publication voluntary self-overrides remain a separate ACK-controlled flow.
    """
    if day in person.unavailable:
        return True
    if block == "AM":
        return day in person.unavailable_am
    if block == "PM":
        return day in person.unavailable_pm
    return day in person.unavailable_am or day in person.unavailable_pm


def absolute_unavailable_for_block(person: Person, day: int, block: str) -> bool:
    """ABSOLUTE HARD no-work state: never relaxable by the solver."""
    if day in person.vacation or day in person.justified_absence:
        return True
    # A marked >12-24h / 24h duty starts on day N. The following calendar
    # day is conservatively blocked to protect at least 24h post-duty rest.
    # Sentinel 0 is used by the app for a duty on the previous month's last day.
    if (day - 1) in person.long_duty:
        return True
    return False


def hard_unavailable_for_block(person: Person, day: int, block: str) -> bool:
    """Backward-compatible combined view used by forms/audits.

    Solver feasibility itself distinguishes ABSOLUTE HARD from RESIDENT HARD.
    """
    return absolute_unavailable_for_block(person, day, block) or resident_hard_unavailable_for_block(person, day, block)


def normal_assignment_blocked(person: Person, day: int, block: str, include_resident_hard: bool = True) -> bool:
    if absolute_unavailable_for_block(person, day, block):
        return True
    if include_resident_hard and resident_hard_unavailable_for_block(person, day, block):
        return True
    # A self-selected backup slot remains a concrete commitment and blocks an
    # overlapping normal assignment.
    return any(rday == day and blocks_overlap(rblock, block) for rday, rblock in person.reserved_backup)


def absolute_assignment_blocked(person: Person, day: int, block: str) -> bool:
    return normal_assignment_blocked(person, day, block, include_resident_hard=False)


def preferred_for_slot(person: Person, day: int, block: str) -> bool:
    """Whether an assignment matches an explicit monthly work preference."""
    if day in person.preferred:
        return True
    if day in person.preferred_am and blocks_overlap(block, "AM"):
        return True
    if day in person.preferred_pm and blocks_overlap(block, "PM"):
        return True
    return False


def normalize_preferences_against_engine(
    people: List[Person], year: int, month: int
) -> Tuple[List[Person], List[dict]]:
    """Remove redundant/impossible SOFT signals before optimization.

    This is deliberately conservative: genuinely individual information stays.
    Only a SOFT request that is already guaranteed by HARD logic, impossible
    under HARD logic, internally contradictory, or exactly duplicated by a
    global engine rule is removed from the objective.
    """
    normalized: List[Person] = []
    audit: List[dict] = []
    ndays = calendar.monthrange(year, month)[1]

    def valid_day(d):
        return isinstance(d, int) and 1 <= d <= ndays

    for p in people:
        q = replace(
            p,
            unavailable=set(p.unavailable),
            unavailable_am=set(p.unavailable_am),
            unavailable_pm=set(p.unavailable_pm),
            vacation=set(p.vacation),
            justified_absence=set(p.justified_absence),
            long_duty=set(p.long_duty),
            reserved_backup=set(p.reserved_backup),
            soft_free=set(p.soft_free),
            soft_free_am=set(p.soft_free_am),
            soft_free_pm=set(p.soft_free_pm),
            preferred=set(p.preferred),
            preferred_am=set(p.preferred_am),
            preferred_pm=set(p.preferred_pm),
            prior_rotation_counts=dict(p.prior_rotation_counts),
            request_items=[dict(x) for x in (p.request_items or [])],
        )

        # Drop invalid calendar dates from SOFT objective.
        for attr in ("soft_free","soft_free_am","soft_free_pm","preferred","preferred_am","preferred_pm"):
            vals=set(getattr(q,attr))
            bad={d for d in vals if not valid_day(d)}
            if bad:
                setattr(q,attr,vals-bad)
                audit.append({"initials":p.initials,"type":"invalid_date","item":attr,"days":sorted(bad)})

        # SOFT-free requests already guaranteed by HARD are redundant.
        redundant_full={d for d in q.soft_free if hard_unavailable_for_block(q,d,"FULL")}
        redundant_am={d for d in q.soft_free_am if hard_unavailable_for_block(q,d,"AM")}
        redundant_pm={d for d in q.soft_free_pm if hard_unavailable_for_block(q,d,"PM")}
        q.soft_free-=redundant_full
        q.soft_free_am-=redundant_am
        q.soft_free_pm-=redundant_pm
        for item,days in (("soft_free",redundant_full),("soft_free_am",redundant_am),("soft_free_pm",redundant_pm)):
            if days:
                audit.append({"initials":p.initials,"type":"covered_by_HARD","item":item,"days":sorted(days)})

        # Work wishes that HARD makes impossible must not depress preference % or
        # waste objective effort. They are ignored, not converted into HARD.
        impossible_full={
            d for d in q.preferred
            if normal_assignment_blocked(q,d,"AM") and normal_assignment_blocked(q,d,"PM")
        }
        impossible_am={d for d in q.preferred_am if normal_assignment_blocked(q,d,"AM")}
        impossible_pm={d for d in q.preferred_pm if normal_assignment_blocked(q,d,"PM")}
        q.preferred-=impossible_full
        q.preferred_am-=impossible_am
        q.preferred_pm-=impossible_pm
        for item,days in (("preferred",impossible_full),("preferred_am",impossible_am),("preferred_pm",impossible_pm)):
            if days:
                audit.append({"initials":p.initials,"type":"blocked_by_HARD","item":item,"days":sorted(days)})

        # Exact self-contradictions on the same scope are neutralized rather than
        # making the solver spend effort rewarding and penalizing the same thing.
        both_full=q.preferred & q.soft_free
        both_am=q.preferred_am & q.soft_free_am
        both_pm=q.preferred_pm & q.soft_free_pm
        q.preferred-=both_full; q.soft_free-=both_full
        q.preferred_am-=both_am; q.soft_free_am-=both_am
        q.preferred_pm-=both_pm; q.soft_free_pm-=both_pm
        for item,days in (("FULL work/free conflict",both_full),("AM work/free conflict",both_am),("PM work/free conflict",both_pm)):
            if days:
                audit.append({"initials":p.initials,"type":"self_conflict_neutralized","item":item,"days":sorted(days)})

        # V2.5.102 persistent directional work-style settings are preserved.
        # Weekend direction is a SOFT tie-breaker only *inside* the already locked
        # raw Saturday/Sunday water-fill corridor, so it cannot dump extra burden
        # onto peers or widen SYSTEM fairness.
        q.weekday_preference=max(-2,min(2,int(getattr(q,"weekday_preference",0) or 0)))
        q.weekend_preference=max(-2,min(2,int(getattr(q,"weekend_preference",0) or 0)))
        if q.weekday_preference or q.weekend_preference:
            audit.append({
                "initials":p.initials,"type":"structured_directional_workstyle_preserved",
                "item":"weekday/weekend pattern","days":[],
            })

        # V2.5.70 persistent workday-length preference. It is personal and
        # shapes AM+PM pairing only after absolute work/rest feasibility.
        q.shift_length_preference=max(0,min(3,int(getattr(q,"shift_length_preference",0) or 0)))
        if q.shift_length_preference==1:
            q.avoid_doubles=True
        elif q.shift_length_preference in (2,3):
            q.avoid_doubles=False
        if q.shift_length_preference:
            audit.append({
                "initials":p.initials,
                "type":"structured_workstyle_preserved",
                "item":"shift_length_preference",
                "value":q.shift_length_preference,
                "days":[],
            })
        elif q.avoid_doubles:
            audit.append({
                "initials":p.initials,
                "type":"legacy_structured_soft1_preserved",
                "item":"avoid_doubles",
                "days":[],
            })

        normalized.append(q)

    return normalized, audit



def serialize_people_request_snapshot(people: List[Person]) -> dict:
    """JSON-safe frozen request/satisfaction input for a generated schedule.

    The snapshot is intentionally limited to resident-request and satisfaction
    fields. Operational fairness history remains sourced from the published
    SYSTEM ledger and is not rewritten by later swaps.
    """
    rows=[]
    set_fields=(
        "unavailable","unavailable_am","unavailable_pm","vacation","justified_absence",
        "long_duty","soft_free","soft_free_am","soft_free_pm","preferred",
        "preferred_am","preferred_pm",
    )
    for p in people:
        row={
            "initials":p.initials,"name":p.name,
            "target_adjustment":int(p.target_adjustment),
            "weekday_preference":int(p.weekday_preference),
            "weekend_preference":int(p.weekend_preference),
            "holiday_preference":int(p.holiday_preference),
            "spread_preference":int(p.spread_preference),
            "shift_length_preference":int(getattr(p,"shift_length_preference",0) or 0),
            "avoid_doubles":bool(p.avoid_doubles),
            "rest_credit_am_to_use":int(p.rest_credit_am_to_use),
            "rest_credit_pm_to_use":int(p.rest_credit_pm_to_use),
            "prior_resident_hard_loss_count":int(p.prior_resident_hard_loss_count),
            "prior_weekend_count":int(p.prior_weekend_count),
            "prior_holiday_count":int(p.prior_holiday_count),
            "prior_friday_count":int(p.prior_friday_count),
            "prior_double_count":int(p.prior_double_count),
            "prior_weekday_day_count":int(p.prior_weekday_day_count),
            "prior_rotation_counts":dict(p.prior_rotation_counts),
            "prior_consecutive_weekend_streak":int(p.prior_consecutive_weekend_streak),
            "prior_last_day_onko":bool(getattr(p,"prior_last_day_onko",False)),
            "request_items":[dict(x) for x in (p.request_items or [])],
            "reserved_backup":[[int(d),str(b)] for d,b in sorted(p.reserved_backup)],
        }
        for f in set_fields:
            row[f]=sorted(int(x) for x in getattr(p,f))
        rows.append(row)
    return {"schema":"V2558_ORIGINAL_REQUEST_SNAPSHOT","people":rows}


def people_from_request_snapshot(snapshot: Optional[dict]) -> List[Person]:
    """Restore only the frozen request model needed for satisfaction scoring."""
    if not snapshot or not isinstance(snapshot,dict):
        return []
    out=[]
    for r in snapshot.get("people",[]) or []:
        try:
            out.append(Person(
                initials=str(r.get("initials") or ""),
                name=str(r.get("name") or r.get("initials") or ""),
                unavailable=set(r.get("unavailable") or []),
                unavailable_am=set(r.get("unavailable_am") or []),
                unavailable_pm=set(r.get("unavailable_pm") or []),
                vacation=set(r.get("vacation") or []),
                justified_absence=set(r.get("justified_absence") or []),
                long_duty=set(r.get("long_duty") or []),
                reserved_backup={tuple(x) for x in (r.get("reserved_backup") or []) if len(x)==2},
                soft_free=set(r.get("soft_free") or []),
                soft_free_am=set(r.get("soft_free_am") or []),
                soft_free_pm=set(r.get("soft_free_pm") or []),
                preferred=set(r.get("preferred") or []),
                preferred_am=set(r.get("preferred_am") or []),
                preferred_pm=set(r.get("preferred_pm") or []),
                target_adjustment=int(r.get("target_adjustment") or 0),
                request_items=[dict(x) for x in (r.get("request_items") or [])],
                rest_credit_am_to_use=int(r.get("rest_credit_am_to_use") or 0),
                rest_credit_pm_to_use=int(r.get("rest_credit_pm_to_use") or 0),
                weekday_preference=int(r.get("weekday_preference") or 0),
                weekend_preference=int(r.get("weekend_preference") or 0),
                holiday_preference=max(-1,min(1,int(r.get("holiday_preference") or 0))),
                spread_preference=int(r.get("spread_preference") or 0),
                shift_length_preference=max(0,min(3,int(r.get("shift_length_preference") or 0))),
                avoid_doubles=bool(r.get("avoid_doubles",False)),
                prior_resident_hard_loss_count=int(r.get("prior_resident_hard_loss_count") or 0),
                prior_weekend_count=int(r.get("prior_weekend_count") or 0),
                prior_holiday_count=int(r.get("prior_holiday_count") or 0),
                prior_friday_count=int(r.get("prior_friday_count") or 0),
                prior_double_count=int(r.get("prior_double_count") or 0),
                prior_weekday_day_count=int(r.get("prior_weekday_day_count") or 0),
                prior_rotation_counts=dict(r.get("prior_rotation_counts") or {}),
                prior_consecutive_weekend_streak=int(r.get("prior_consecutive_weekend_streak") or 0),
                prior_last_day_onko=bool(r.get("prior_last_day_onko",False)),
            ))
        except Exception:
            continue
    return out


def _fallback_request_items(person: Person, year: int, month: int) -> List[dict]:
    """Synthesize a ledger for research imports/legacy payloads without metadata."""
    items=[]
    def add(kind,tier,day=None,block="FULL",source="effective",score=True,value=None):
        items.append({
            "kind":kind,"tier":tier,"day":day,"block":block,"source":source,
            "included_in_score":bool(score),"value":value,
        })
    for d in sorted(person.unavailable): add("resident_hard","RESIDENT_HARD",d,"FULL")
    for d in sorted(person.unavailable_am): add("resident_hard","RESIDENT_HARD",d,"AM")
    for d in sorted(person.unavailable_pm): add("resident_hard","RESIDENT_HARD",d,"PM")
    for d in sorted(person.soft_free): add("soft_free","SOFT1_TIME_PROTECTION",d,"FULL")
    for d in sorted(person.soft_free_am): add("soft_free","SOFT1_TIME_PROTECTION",d,"AM")
    for d in sorted(person.soft_free_pm): add("soft_free","SOFT1_TIME_PROTECTION",d,"PM")
    for d in sorted(person.preferred): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"FULL")
    for d in sorted(person.preferred_am): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"AM")
    for d in sorted(person.preferred_pm): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"PM")
    # V2.5.102 persistent work-style settings are scored as SOFT3. Weekend
    # direction can only choose inside the structural Saturday/Sunday corridor.
    if person.weekday_preference: add("weekday_preference","SOFT3_SCHEDULE_SHAPE",source="account_settings",value=int(person.weekday_preference))
    if person.weekend_preference: add("weekend_preference","SOFT3_SCHEDULE_SHAPE",source="account_settings",value=int(person.weekend_preference))
    if person.spread_preference: add("spread_preference","SOFT3_SCHEDULE_SHAPE",source="account_settings",value=int(person.spread_preference))
    if person.holiday_preference and public_holiday_days_in_month(year,month):
        add("holiday_preference","SOFT_HOLIDAY",source="account_settings",value=int(person.holiday_preference))
    shift_len=max(0,min(3,int(getattr(person,"shift_length_preference",0) or 0)))
    if shift_len:
        add("shift_length_preference","SOFT1_TIME_PROTECTION" if shift_len==1 else "SOFT3_SCHEDULE_SHAPE",source="account_settings",value=shift_len)
    elif person.avoid_doubles:
        add("avoid_doubles","SOFT1_TIME_PROTECTION",source="account_settings",value=True)
    for d in sorted(person.vacation): add("vacation","ABSOLUTE_HARD",d,"FULL",score=False)
    for d in sorted(person.justified_absence): add("justified_absence","ABSOLUTE_HARD",d,"FULL",score=False)
    for d in sorted(person.long_duty): add("long_duty","ABSOLUTE_HARD",d,"FULL",score=False)
    for n in range(max(0,int(person.rest_credit_am_to_use))): add("rest_credit","ENTITLEMENT",source="rest_credit",value="AM")
    for n in range(max(0,int(person.rest_credit_pm_to_use))): add("rest_credit","ENTITLEMENT",source="rest_credit",value="PM")
    return items


def _request_kind_label(kind: str) -> str:
    return {
        "resident_hard":"Negaliu dirbti",
        "soft_free":"Noriu laisvos",
        "preferred":"Pageidauju dirbti",
        "weekday_preference":"Darbo dienų kryptis",
        "weekend_preference":"Savaitgalių kryptis",
        "holiday_preference":"Švenčių dienų pasirinkimas",
        "spread_preference":"Išsklaidymas / koncentracija",
        "shift_length_preference":"Pageidaujama darbo dienos trukmė",
        "avoid_doubles":"Vengti dublių",
        "backup_claim":"Pasirinktas dublis",
        "rest_credit":"Poilsio kredito panaudojimas",
        "vacation":"Atostogos",
        "justified_absence":"Pateisinamas neatvykimas",
        "long_duty":"Ilgas / naktinis budėjimas",
        "note":"Papildomas komentaras",
    }.get(kind,kind)



ROTATION_CATEGORIES = (
    "CENTRO RO",
    "Onko RO",
    "SPS RO",
    "Centro UG",
    "SPS UG",
    "ADC 144",
    "ADC 145",
    "Vaikų UG",
    "Mamografijos",
)

# V2.5.52 structural hierarchy. SPS RO, SPS UG and weekend duties are
# co-equal CRITICAL exposure categories. Their count spread is protected before
# RESIDENT HARD and may not be traded for ordinary SOFT satisfaction.
CRITICAL_ROTATION_CATEGORIES = ("SPS RO", "SPS UG")
# V2.5.74: Onko is governed by its own even-pair parity rule (0/2/4...) and
# therefore cannot share the generic <=1 post-waterfill corridor. Every other
# ordinary workplace is structurally water-filled across residents.
NONCRITICAL_ROTATION_CATEGORIES = tuple(c for c in ROTATION_CATEGORIES if c not in CRITICAL_ROTATION_CATEGORIES and c != "Onko RO")
CRITICAL_SPREAD_TARGET = 1
NONCRITICAL_SPREAD_NORMAL_CEILING = 1
NONCRITICAL_SPREAD_EXCEPTIONAL_CEILING = 2
NONCRITICAL_SPREAD_LAST_RESORT_CEILING = 3
# V2.5.71: same-day AM+PM double burden is a structural group property.
# Personal 6h/12h work-style preferences may redistribute existing doubles,
# but may not widen the monthly resident-to-resident double spread beyond 2.
DOUBLE_SPREAD_MAX = 2

# Internal allocation priority. Not part of resident preference scoring/UI.
_PRIORITY_COLOCATION_GROUP = ("SP", "GE", "ŠR")
_PRIORITY_COLOCATION_MAX_PER_MONTH = 6

# V2.5.53 WEEKLY LOAD / RECOVERY CONSTITUTION.
# These are safety/fatigue guardrails, not user-selectable SOFT preferences.
# The Rule Profile may tighten them, but cannot weaken them.
FATIGUE_MAX_WORKDAYS_ROLLING7 = 6
FATIGUE_ROLLING7_HARD_CEILING_HOURS = 48.0
WEEKLY_LOAD_SOFT_TARGET_HOURS = 40.0

# V2.5.55 voluntary-swap reality guardrails. Generation remains deliberately
# stricter (48h/7d + recovery shaping), but a bilateral post-publication swap
# may use the wider legal/operational envelope below. Acknowledgement never
# overrides these blockers.
SWAP_ABSOLUTE_MAX_HOURS_ROLLING7 = 60.0
SWAP_MAX_WORKDAYS_ROLLING7 = 6
SWAP_MIN_DAILY_REST_HOURS = 11.0
SWAP_MAX_HOURS_PER_DAY = 12.0
SWAP_WEEKLY_REST_PROXY_HOURS = 35.0

def backup_required_slot(slot: Slot) -> bool:
    """Mandatory named-backup scope for publication readiness.

    V2.5.98 is position-based rather than weekend-based. SPS RO and SPS UG
    require cover on every day/block in which those positions exist. Centro 120
    requires cover for AM only; Onko RO requires one backup for the full 9h shift.
    A future night shift therefore inherits SPS RO/SPS UG coverage automatically
    without adding a separate weekday/weekend rule.
    """
    if slot.blocked:
        return False
    if slot.department == "Onko RO centre":
        return bool(rule_value("backup_onko_ro"))
    if slot.department.startswith("Centro UG 120") and slot.block == "AM":
        return bool(rule_value("backup_centro120_am"))
    if slot.department.startswith("SPS RO"):
        return bool(rule_value("backup_sps_ro"))
    if slot.department.startswith("SPS UG"):
        return bool(rule_value("backup_sps_ug"))
    return False


def backup_best_effort_slot(slot: Slot) -> bool:
    """Non-blocking backup objective: cover CENTRO RO as much as capacity allows."""
    return bool(
        (not slot.blocked)
        and slot.department.startswith("CENTRO RO")
        and rule_value("backup_centro_ro_best_effort")
    )


def rotation_category(slot: Slot) -> str:
    """Canonical workplace group used for monthly diversity and longitudinal balancing."""
    d=slot.department
    if d.startswith("CENTRO RO"):
        return "CENTRO RO"
    if d.startswith("Onko RO"):
        return "Onko RO"
    if d.startswith("SPS RO"):
        return "SPS RO"
    if d.startswith("Centro UG"):
        return "Centro UG"
    if d.startswith("SPS UG"):
        return "SPS UG"
    if d.startswith("ADC 144"):
        return "ADC 144"
    if d.startswith("145") or d.startswith("ADC 145"):
        return "ADC 145"
    if d.startswith("Vaikų UG"):
        return "Vaikų UG"
    if d.startswith("Mamografijos"):
        return "Mamografijos"
    return d

# V2.5.56 emergency / post-publication critical-cover hierarchy.
# If a resident becomes unavailable after publication, SPS RO / SPS UG / weekend
# SPS RO coverage is preserved first. On weekdays the preferred rescue is a
# same-block transfer from a currently staffed, non-mandatory lower-priority post;
# that donor's optional source post may be left empty. This keeps the critical
# service covered without unnecessarily adding a new shift to a free resident.
EMERGENCY_CRITICAL_ROTATIONS = ("SPS RO", "SPS UG")


def is_emergency_critical_slot(slot: Slot) -> bool:
    return (not slot.blocked) and rotation_category(slot) in EMERGENCY_CRITICAL_ROTATIONS


def is_emergency_lower_priority_donor_slot(slot: Slot) -> bool:
    """Whether this staffed slot may be sacrificed to rescue SPS RO / SPS UG.

    Onko is excluded even in odd-weekday months because its monthly coverage has
    its own structural rule. Critical SPS slots and all mandatory rows are never
    donors. Explicitly blocked rows are not real staffed capacity.
    """
    if slot.blocked or slot.mandatory:
        return False
    if slot.department == "Onko RO centre":
        return False
    return rotation_category(slot) not in EMERGENCY_CRITICAL_ROTATIONS


def emergency_donor_source_slots(
    slots: List[Slot], assignments: Dict[int, str], target_slot: Slot, replacement: str
) -> List[Slot]:
    """Same-time optional posts from which ``replacement`` can be pulled.

    The source must overlap the critical target block on the same day so the
    repair is a true transfer rather than an additional workload assignment.
    """
    out=[]
    for sl in slots:
        if assignments.get(sl.idx) != replacement:
            continue
        if sl.day != target_slot.day:
            continue
        if not blocks_overlap(sl.block, target_slot.block):
            continue
        if not is_emergency_lower_priority_donor_slot(sl):
            continue
        out.append(sl)
    return sorted(out, key=lambda sl:(sl.day, sl.department, sl.block, sl.idx))


def apply_emergency_critical_transfer(
    assignments: Dict[int, str], target_slot: Slot, replacement: str, source_slot: Optional[Slot] = None
) -> Dict[int, str]:
    """Return a repaired assignment map for one critical-cover transfer.

    If ``source_slot`` is provided, it is intentionally vacated and the same
    resident is moved into ``target_slot``. The caller remains responsible for
    ABSOLUTE-HARD / rest / overlap / coverage validation.
    """
    new_assign=dict(assignments)
    if source_slot is not None:
        if new_assign.get(source_slot.idx) != replacement:
            raise ValueError("Emergency donor source is not assigned to replacement")
        if source_slot.day != target_slot.day or not blocks_overlap(source_slot.block, target_slot.block):
            raise ValueError("Emergency donor source must overlap target on the same day")
        if not is_emergency_lower_priority_donor_slot(source_slot):
            raise ValueError("Emergency donor source is not a lower-priority optional post")
        new_assign.pop(source_slot.idx, None)
    new_assign[target_slot.idx]=replacement
    return new_assign


def make_slots(year: int, month: int) -> List[Slot]:
    """
    Current department model from the group's supplied rules.

    Weekdays:
      CENTRO RO 4x AM + 4x PM
      Onko RO centre FULL, workload 1.5
      Centro UG 120kab AM + PM (PM appended after legacy rows to preserve historical slot IDs)
      SPS RO d.d. AM
      SPS UG 1035kab AM + PM
      ADC 144kab AM + PM
      145kab AM + PM
      Vaikų UG 1019kab AM
      Mamografijos 31kab AM + PM (PM blocked Fridays)

    Weekends:
      SPS RO budėjimai AM + PM

    Coverage:
      SPS RO d.d., SPS UG and weekend SPS RO duties are mandatory.
      Other administrative rows may be left empty when required by exact monthly workload,
      but optional gaps are dispersed (max 1 per weekday).
      Explicit closure exceptions remain blocked (currently Mamografijos PM Fridays).
    Onko:
      If the month has an even number of weekdays -> every weekday filled.
      If odd -> exactly one weekday Onko slot may stay empty.
    """
    slots: List[Slot] = []
    idx = 0
    _, ndays = calendar.monthrange(year, month)
    odd_weekdays = weekday_count(year, month) % 2 == 1

    def add(day, wd, dept, block, workload2=2, mandatory=False, blocked=False):
        nonlocal idx
        slots.append(Slot(
            idx=idx, day=day, weekday=wd, department=dept, block=block,
            workload2=workload2, mandatory=mandatory, blocked=blocked
        ))
        idx += 1

    holiday_days=public_holiday_days_in_month(year,month)
    weekday_holidays=[]
    centro120_pm_days=[]
    for d in range(1, ndays + 1):
        wd = date(year, month, d).weekday()
        if wd < 5:
            # V2.5.58 backward-compatible slot identity:
            # Keep the legacy weekday rows (and therefore every historical slot id)
            # even on a statutory holiday, but mark all ordinary outpatient rows
            # CLOSED/BLOCKED. The two live SPS RO holiday-duty rows are appended only
            # after every legacy day row has been created. This prevents a weekday
            # holiday from shifting ids in already-published SYSTEM baselines.
            holiday_closed = d in holiday_days
            for k in range(1, 5):
                add(d, wd, f"CENTRO RO {k}", "AM", blocked=holiday_closed)
            for k in range(1, 5):
                add(d, wd, f"CENTRO RO {k}", "PM", blocked=holiday_closed)
            add(d, wd, "Onko RO centre", "FULL", workload2=3, mandatory=(not holiday_closed and not odd_weekdays), blocked=holiday_closed)
            add(d, wd, "Centro UG 120kab", "AM", blocked=holiday_closed)
            # V2.5.97: remember the new PM shift but append it only after every
            # pre-existing slot. Historical published JSON uses numeric slot IDs,
            # so inserting it here would corrupt old schedules.
            centro120_pm_days.append((d,wd,holiday_closed))
            add(d, wd, "SPS RO d.d.", "AM", mandatory=(not holiday_closed), blocked=holiday_closed)
            add(d, wd, "SPS UG 1035kab", "AM", mandatory=(not holiday_closed), blocked=holiday_closed)
            add(d, wd, "SPS UG 1035kab", "PM", mandatory=(not holiday_closed), blocked=holiday_closed)
            add(d, wd, "ADC 144kab", "AM", blocked=holiday_closed)
            add(d, wd, "ADC 144kab", "PM", blocked=holiday_closed)
            add(d, wd, "145kab", "AM", blocked=holiday_closed)
            add(d, wd, "145kab", "PM", blocked=holiday_closed)
            add(d, wd, "Vaikų UG 1019kab", "AM", blocked=holiday_closed)
            add(d, wd, "Mamografijos 31kab", "AM", blocked=holiday_closed)
            add(d, wd, "Mamografijos 31kab", "PM", blocked=(holiday_closed or wd == 4))
            if holiday_closed:
                weekday_holidays.append((d,wd))
        else:
            add(d, wd, "SPS RO budėjimai", "AM", mandatory=True)
            add(d, wd, "SPS RO budėjimai", "PM", mandatory=True)

    # Add live weekday-holiday emergency duty rows *after* the legacy slot block.
    # Weekend holidays already use the normal weekend SPS RO duty rows above.
    for d,wd in weekday_holidays:
        add(d, wd, "SPS RO budėjimai", "AM", mandatory=True)
        add(d, wd, "SPS RO budėjimai", "PM", mandatory=True)

    # V2.5.97 NEW CAPACITY — append-only identity rule.
    for d,wd,holiday_closed in centro120_pm_days:
        add(d, wd, "Centro UG 120kab", "PM", blocked=bool(holiday_closed))
    return slots


class ModelBuilder:
    def __init__(self):
        self.c: List[float] = []
        self.lb: List[float] = []
        self.ub: List[float] = []
        self.integrality: List[int] = []
        self.names: List[str] = []
        self.rows: List[Tuple[Dict[int, float], float, float, str]] = []

    def var(self, name, cost=0.0, lb=0.0, ub=1.0, integer=True) -> int:
        i = len(self.c)
        self.c.append(float(cost))
        self.lb.append(float(lb))
        self.ub.append(float(ub))
        self.integrality.append(1 if integer else 0)
        self.names.append(name)
        return i

    def constraint(self, coeffs: Dict[int, float], low=-np.inf, high=np.inf, label=""):
        self.rows.append((coeffs, float(low), float(high), label))

    def solve(self, time_limit=45.0):
        # V2.5.64 PERFORMANCE: build the sparse matrix directly in COO/CSR form.
        # The previous LIL cell-by-cell builder became the dominant wall-clock
        # cost after several staged fairness locks; scipy's time_limit only applies
        # after the matrix has been constructed. Direct COO assembly keeps repeated
        # verification solves responsive without changing a single constraint.
        n = len(self.c)
        m = len(self.rows)
        row_idx=[]
        col_idx=[]
        data=[]
        lows=np.empty(m,dtype=float)
        highs=np.empty(m,dtype=float)
        for r,(co,lo,hi,_) in enumerate(self.rows):
            lows[r]=lo; highs[r]=hi
            if co:
                row_idx.extend([r]*len(co))
                col_idx.extend(co.keys())
                data.extend(co.values())
        A=csr_matrix((np.asarray(data,dtype=float),(np.asarray(row_idx,dtype=np.int32),np.asarray(col_idx,dtype=np.int32))),shape=(m,n))
        return milp(
            c=np.asarray(self.c),
            integrality=np.asarray(self.integrality),
            bounds=Bounds(np.asarray(self.lb), np.asarray(self.ub)),
            constraints=LinearConstraint(A, lows, highs),
            options={"time_limit": time_limit, "presolve": True},
        )


def calculate_targets(year: int, month: int, people: List[Person]) -> Dict[str, int]:
    """Canonical exact monthly targets used by both solver and live revalidation."""
    targets={}
    _, target_ndays=calendar.monthrange(year,month)
    for p in people:
        holiday_days=public_holiday_days_in_month(year,month)
        justified_weekdays=sum(
            1 for d in (set(p.vacation) | set(p.justified_absence))
            if 1 <= d <= target_ndays and date(year,month,d).weekday() < 5 and d not in holiday_days
        )
        adjusted_base=round_half_up(
            max(0,weekday_count(year,month)-justified_weekdays)
            * float(rule_value("target_daily_hours"))
            / float(rule_value("target_shift_hours"))
        )
        targets[p.initials]=max(0,adjusted_base+p.target_adjustment)
    return targets


def plan_distributed_gaps(
    year: int, month: int, people: List[Person], slots: List[Slot], targets: Dict[str, int]
) -> Tuple[Set[int], dict, List[str]]:
    """Plan WHEN optional rows may remain open while keeping gaps dispersed.

    V2.5.65 vacation support may lower several residents' monthly targets enough
    that there are more optional gaps than weekday dates. The older planner
    hard-failed in that situation because it allowed at most one gap per day.
    The new planner distributes the required gaps as evenly as possible: every
    weekday gets the same base number of gaps, then the remainder is spread
    across the month. Mandatory rows are never selected as gaps.
    """
    errors=[]
    nonblocked=[s for s in slots if not s.blocked]
    full_supply2=sum(s.workload2 for s in nonblocked)
    target_total2=int(round(sum(float(v) for v in targets.values())*2))

    onko=[s for s in slots if s.department=="Onko RO centre" and not s.blocked]
    # Legacy parity gap is only relevant when the legacy even-count rule is active.
    onko_gap_count=(0 if len(onko)%2==0 else 1) if bool(rule_value("onko_even_required")) else 0
    residual2=full_supply2-target_total2-(3*onko_gap_count)

    if residual2 < 0:
        return set(),{},[f"Target workload exceeds available open-slot workload by {-residual2/2:g}."]
    if residual2 % 2 != 0:
        return set(),{},[f"Optional-gap workload mismatch ({residual2}/2 shift units)."]

    optional_gap_count=int(residual2//2)
    holiday_days=public_holiday_days_in_month(year,month)
    weekdays=sorted({
        s.day for s in slots if s.weekday<5 and s.day not in holiday_days and not s.blocked
    })
    if optional_gap_count and not weekdays:
        return set(),{},["Gap-dispersion impossible: no eligible weekday dates."]

    def eligible_count(slot):
        return sum(
            1 for p in people
            if not normal_assignment_blocked(p,slot.day,slot.block)
        )

    fixed_gap_ids=set()
    onko_gap_day=None
    if onko_gap_count:
        chosen_onko=min(
            onko,
            key=lambda s:(
                eligible_count(s),
                abs(s.day-(calendar.monthrange(year,month)[1]+1)/2),
                s.day,
            )
        )
        fixed_gap_ids.add(chosen_onko.idx)
        onko_gap_day=chosen_onko.day

    candidate_days=list(weekdays)
    n=len(candidate_days)
    k=optional_gap_count
    gap_counts={d:0 for d in candidate_days}
    if k>0:
        # Capacity is the number of optional 6h rows that may legally remain open.
        capacities={
            d:sum(1 for s in slots if s.day==d and not s.blocked and not s.mandatory and s.department!="Onko RO centre")
            for d in candidate_days
        }
        if sum(capacities.values()) < k:
            return set(),{},[
                f"Gap-dispersion impossible: need {k} optional 6h gaps but only {sum(capacities.values())} optional rows exist."
            ]

        # Fill in layers. One gap on every possible day before a second gap is
        # added anywhere; within each layer extras are spaced across the month.
        remaining=k
        layer=0
        while remaining>0:
            eligible=[d for d in candidate_days if capacities[d]>gap_counts[d]]
            if not eligible:
                return set(),{},[f"Gap-dispersion impossible after allocating {k-remaining} of {k} gaps."]
            take=min(remaining,len(eligible))
            if take==len(eligible):
                chosen=eligible
            else:
                target_positions=[((j+0.5)*len(eligible)/take)-0.5 for j in range(take)]
                unused=set(range(len(eligible))); pos=[]
                for t in target_positions:
                    q=min(unused,key=lambda q:(abs(q-t),q))
                    pos.append(q); unused.remove(q)
                chosen=[eligible[q] for q in sorted(pos)]
            for d in chosen:
                gap_counts[d]+=1
            remaining-=len(chosen)
            layer+=1

    gap_days=[d for d in candidate_days if gap_counts.get(d,0)>0]
    meta={
        "planned_gap_count":optional_gap_count+onko_gap_count,
        "optional_gap_count":optional_gap_count,
        "onko_gap_count":onko_gap_count,
        "optional_gap_days":sorted(gap_days),
        "optional_gap_counts":{int(d):int(c) for d,c in gap_counts.items() if c>0},
        "max_optional_gaps_one_day":max(list(gap_counts.values())+[0]),
        "onko_gap_day":onko_gap_day,
        "gap_days":sorted(set(gap_days+([onko_gap_day] if onko_gap_day else []))),
    }
    return fixed_gap_ids,meta,errors


def _balanced_stats_penalty(stats: Dict[str,dict]) -> float:
    """Lower is better; strict fallback quality ordering for V2.5.48.

    The old fallback could trade one very bad workplace spread for several small
    improvements elsewhere because it mostly looked at the *sum* of post spread.
    That is exactly the failure pattern seen in the research shadow run (for
    example a resident range such as 8..14 in CENTRO RO).  The fallback now
    follows the same policy as the MILP:

      TRUE ABSOLUTE HARD -> SYSTEM-HARD worst monthly post spread -> total
      nine-post spread -> RESIDENT-HARD burden -> worst active preference
      fulfilment -> mean active preference fulfilment -> remaining fairness.

    This is only used when the global fairness MILP has no incumbent in time, but
    it must still protect the constitutional priorities instead of exposing an
    arbitrary HARD-valid schedule.
    """
    g=(stats or {}).get("global",{})
    if int(g.get("hard_errors",9999)):
        return 1e12+1e9*int(g.get("hard_errors",9999))
    rh_total=float(g.get("resident_hard_total_losses",0) or 0)
    rh_max=float(g.get("resident_hard_max_loss_per_resident",0) or 0)
    rh_cum_spread=float(g.get("resident_hard_cumulative_spread",0) or 0)
    post_spreads=g.get("rotation_monthly_spreads") or {}
    worst_post=max([float(v) for v in post_spreads.values()] + [0.0])
    post_total=float(g.get("rotation_monthly_imbalance",9999))
    pref_min=g.get("min_preference_score")
    pref_mean=g.get("mean_preference_score")
    pref_min_penalty=0.0 if pref_min is None else (100.0-float(pref_min))*35.0
    pref_mean_penalty=0.0 if pref_mean is None else (100.0-float(pref_mean))*3.0
    monthly=(100.0-float(g.get("monthly_fairness_score",0.0)))*4.0
    diversity=max(0.0,9.0-float(g.get("mean_distinct_rotations",0.0)))*5.0
    cumulative=(100.0-float(g.get("cumulative_fairness_score",0.0)))*0.5
    return (
        worst_post*1000000000000.0
        + post_total*10000000000.0
        + rh_total*100000000.0
        + rh_max*10000000.0
        + rh_cum_spread*1000000.0
        + pref_min_penalty
        + pref_mean_penalty
        + monthly
        + diversity
        + cumulative
    )


def local_fairness_repair(
    year: int, month: int, people: List[Person], assignments: Dict[int,str],
    targets: Dict[str,int], seconds: float = 8.0
) -> Tuple[Dict[int,str], Dict[str,dict], int]:
    """Fast best-so-far repair loop for a HARD-valid incumbent.

    It swaps equal-workload assignments, so per-person target workload remains exact.
    Every candidate is revalidated against the full current HARD engine.
    The loop is deterministic for the month and only accepts strictly better balanced
    candidates. This gives the web app a useful fallback even when the global MILP
    fairness stage times out.
    """
    import random, time as _time

    slots=make_slots(year,month)
    slot_by_id={s.idx:s for s in slots}
    person_by_initials={p.initials:p for p in people}
    current=dict(assignments)
    current_stats=validate_schedule(year,month,people,slots,current,targets)
    if current_stats["global"]["hard_errors"]:
        return current,current_stats,0

    current_penalty=_balanced_stats_penalty(current_stats)
    assigned_ids=[sid for sid in current if sid in slot_by_id]
    rng=random.Random((year*100+month)*7919+len(assigned_ids))
    deadline=_time.monotonic()+max(0.5,float(seconds))
    accepted=0
    attempts=0

    # Pass 1: high-value, very safe workplace swaps inside the same day/block.
    pairs=[]
    by_day_block={}
    for sid in assigned_ids:
        s=slot_by_id[sid]
        by_day_block.setdefault((s.day,s.block,s.workload2),[]).append(sid)
    for ids in by_day_block.values():
        for a in range(len(ids)):
            for b in range(a+1,len(ids)):
                s1=slot_by_id[ids[a]]; s2=slot_by_id[ids[b]]
                if rotation_category(s1)!=rotation_category(s2):
                    pairs.append((ids[a],ids[b]))
    rng.shuffle(pairs)

    # V2.5.48 targeted POST-SPREAD repair.
    # For every workplace, explicitly try to move one assignment from a resident
    # above the category mean to one below it, using an equal-workload reciprocal
    # swap.  This is much more effective than waiting for a useful random swap.
    # The full HARD validator still decides whether a candidate is admissible.
    post_targeted=[]
    pdata=current_stats["people"]
    person_sids={
        initials:[sid for sid in assigned_ids if current.get(sid)==initials]
        for initials in pdata
    }
    for cat in ROTATION_CATEGORIES:
        counts={
            initials:int((pdata[initials].get("rotation_counts") or {}).get(cat,0))
            for initials in pdata
        }
        ordered_hi=sorted(counts,key=lambda i:(-counts[i],i))
        ordered_lo=sorted(counts,key=lambda i:(counts[i],i))
        for ph in ordered_hi[:8]:
            for pl in ordered_lo[:8]:
                if counts[ph] <= counts[pl]+1:
                    continue
                hi_cat=[sid for sid in person_sids[ph] if rotation_category(slot_by_id[sid])==cat]
                # A reciprocal non-cat assignment keeps both exact monthly workloads
                # unchanged while reducing the selected post spread when feasible.
                lo_other=[sid for sid in person_sids[pl] if rotation_category(slot_by_id[sid])!=cat]
                for sid1 in hi_cat:
                    s1=slot_by_id[sid1]
                    for sid2 in lo_other:
                        s2=slot_by_id[sid2]
                        if s1.workload2!=s2.workload2:
                            continue
                        post_targeted.append((sid1,sid2))
    rng.shuffle(post_targeted)

    # Targeted TRUE-SOFT repair.
    # Build equal-workload swaps that move a resident INTO preferred time or OUT
    # of requested free time while preserving exact monthly workload.
    preference_pairs=[]
    pmodel={p.initials:p for p in people}
    for initials,p in pmodel.items():
        my_sids=[sid for sid in assigned_ids if current.get(sid)==initials]
        other_sids=[sid for sid in assigned_ids if current.get(sid)!=initials]

        def _add_move_into(day,block=None):
            already=any(
                slot_by_id[sid].day==day
                and (block is None or blocks_overlap(slot_by_id[sid].block,block))
                for sid in my_sids
            )
            if already:
                return
            targets_here=[
                sid for sid in other_sids
                if slot_by_id[sid].day==day
                and (block is None or blocks_overlap(slot_by_id[sid].block,block))
            ]
            sources=[sid for sid in my_sids if slot_by_id[sid].day!=day]
            for tgt in targets_here:
                for src in sources:
                    if slot_by_id[tgt].workload2!=slot_by_id[src].workload2:
                        continue
                    preference_pairs.append((
                        src,tgt,
                        0 if rotation_category(slot_by_id[src])==rotation_category(slot_by_id[tgt]) else 1
                    ))

        def _add_move_out(day,block=None):
            bad=[
                sid for sid in my_sids
                if slot_by_id[sid].day==day
                and (block is None or blocks_overlap(slot_by_id[sid].block,block))
            ]
            targets_else=[
                sid for sid in other_sids
                if slot_by_id[sid].day!=day
            ]
            for src in bad:
                for tgt in targets_else:
                    if slot_by_id[tgt].workload2!=slot_by_id[src].workload2:
                        continue
                    preference_pairs.append((
                        src,tgt,
                        0 if rotation_category(slot_by_id[src])==rotation_category(slot_by_id[tgt]) else 1
                    ))

        for d in p.preferred:
            _add_move_into(d,None)
        for d in p.preferred_am:
            _add_move_into(d,"AM")
        for d in p.preferred_pm:
            _add_move_into(d,"PM")
        for d in p.soft_free:
            _add_move_out(d,None)
        for d in p.soft_free_am:
            _add_move_out(d,"AM")
        for d in p.soft_free_pm:
            _add_move_out(d,"PM")

    preference_pairs=sorted(set(preference_pairs),key=lambda t:(t[2],t[0],t[1]))
    pref_pairs=[(a,b) for a,b,_samecat in preference_pairs]

    # Targeted burden repair: move weekend / Friday burden from high-count to
    # low-count residents while preserving workplace category whenever possible.
    def _person_sids(initials):
        return [sid for sid in assigned_ids if current.get(sid)==initials]

    targeted=[]
    for metric,high_filter,low_filter in [
        (
            "weekend_assignments",
            lambda s:s.weekday>=5,
            lambda s:s.weekday<5,
        ),
        (
            "friday_assignments",
            lambda s:s.weekday==4,
            lambda s:s.weekday!=4,
        ),
    ]:
        ordered_hi=sorted(pdata,key=lambda p:(-pdata[p].get(metric,0),p))
        ordered_lo=sorted(pdata,key=lambda p:(pdata[p].get(metric,0),p))
        for ph in ordered_hi[:6]:
            for pl in ordered_lo[:6]:
                if pdata[ph].get(metric,0) <= pdata[pl].get(metric,0)+1:
                    continue
                his=[sid for sid in _person_sids(ph) if high_filter(slot_by_id[sid])]
                los=[sid for sid in _person_sids(pl) if low_filter(slot_by_id[sid])]
                for sid1 in his:
                    s1=slot_by_id[sid1]
                    for sid2 in los:
                        s2=slot_by_id[sid2]
                        if s1.workload2!=s2.workload2:
                            continue
                        if rotation_category(s1)!=rotation_category(s2):
                            continue
                        targeted.append((sid1,sid2))
    rng.shuffle(targeted)
    # `pairs.pop()` consumes from the end.
    # `pairs.pop()` consumes from the end.
    # Priority: worst-post repair -> TRUE SOFT repair -> general workplace
    # mixing -> weekend/Friday refinement.
    pairs=targeted+pairs+list(reversed(pref_pairs))+list(reversed(post_targeted))

    # Pass 2 candidate pool: equal-workload swaps across dates/categories.
    equal_workload={}
    for sid in assigned_ids:
        equal_workload.setdefault(slot_by_id[sid].workload2,[]).append(sid)

    while _time.monotonic()<deadline:
        if pairs:
            sid1,sid2=pairs.pop()
        else:
            pool=rng.choice(list(equal_workload.values()))
            if len(pool)<2:
                continue
            sid1,sid2=rng.sample(pool,2)

        p1=current.get(sid1); p2=current.get(sid2)
        if not p1 or not p2 or p1==p2:
            continue
        s1=slot_by_id[sid1]; s2=slot_by_id[sid2]
        if s1.workload2!=s2.workload2:
            continue
        if absolute_assignment_blocked(person_by_initials[p2],s1.day,s1.block):
            continue
        if absolute_assignment_blocked(person_by_initials[p1],s2.day,s2.block):
            continue

        candidate=dict(current)
        candidate[sid1]=p2
        candidate[sid2]=p1
        stats=validate_schedule(year,month,people,slots,candidate,targets)
        attempts+=1
        if stats["global"]["hard_errors"]:
            continue
        # Legacy local fallback helper. V2.5.52 staged solves do not call this
        # all-post fallback because critical and noncritical post corridors now
        # have different constitutional ranks. If invoked by older workflows, it
        # remains deliberately conservative and never worsens the post matrix.
        cg=current_stats.get("global",{})
        ng=stats.get("global",{})
        csp=cg.get("rotation_monthly_spreads") or {}
        nsp=ng.get("rotation_monthly_spreads") or {}
        cworst=max([int(v) for v in csp.values()] + [0])
        nworst=max([int(v) for v in nsp.values()] + [0])
        ctotal=int(cg.get("rotation_monthly_imbalance",sum(int(v) for v in csp.values())) or 0)
        ntotal=int(ng.get("rotation_monthly_imbalance",sum(int(v) for v in nsp.values())) or 0)
        if nworst > cworst:
            continue
        if nworst == cworst and ntotal > ctotal:
            continue
        # The fallback starts from a post-locked + Resident-HARD-optimized
        # incumbent, so it may improve the post matrix but must never throw away
        # the Resident-HARD result already achieved inside that frontier.
        if int(ng.get("resident_hard_total_losses",0) or 0) > int(cg.get("resident_hard_total_losses",0) or 0):
            continue
        if int(ng.get("resident_hard_max_loss_per_resident",0) or 0) > int(cg.get("resident_hard_max_loss_per_resident",0) or 0):
            continue
        penalty=_balanced_stats_penalty(stats)

        # Protect meaningful active preferences from a fairness-only cleanup.
        # V2.5.48 protects the *worst served active resident* first; a better mean
        # may never be purchased by making the least-satisfied person worse.
        old_min=current_stats["global"].get("min_soft_preference_score")
        new_min=stats["global"].get("min_soft_preference_score")
        if old_min is not None and new_min is not None and new_min < old_min-0.1:
            continue
        old_pref=current_stats["global"].get("mean_soft_preference_score")
        new_pref=stats["global"].get("mean_soft_preference_score")
        if old_pref is not None and new_pref is not None and new_pref < old_pref-1.0:
            continue

        if penalty+1e-9 < current_penalty:
            current=candidate
            current_stats=stats
            current_penalty=penalty
            accepted+=1

    current_stats["global"]["local_repair_accepted_swaps"]=accepted
    current_stats["global"]["local_repair_attempts"]=attempts
    return current,current_stats,accepted



class _V2564FastMB:
    """Small MILP builder for the two-phase fairness-first generator.

    V2.5.64 deliberately separates WHEN a resident works from WHICH post they
    receive. The first model therefore has ~2.5k variables instead of the legacy
    ~14k-variable all-in-one staged model. The second model only labels already
    chosen work blocks with posts. This is both faster and closer to the intended
    constitution: equal post COUNTS are protected while concrete dates remain
    flexible for Resident-HARD and SOFT requests.
    """
    def __init__(self):
        self.c=[]; self.lb=[]; self.ub=[]; self.integrality=[]; self.rows=[]
    def var(self, lb=0.0, ub=1.0, integer=True, cost=0.0):
        i=len(self.c); self.c.append(float(cost)); self.lb.append(float(lb)); self.ub.append(float(ub)); self.integrality.append(1 if integer else 0); return i
    def constraint(self, coeffs, low=-np.inf, high=np.inf):
        self.rows.append((coeffs,float(low),float(high)))
    def solve(self, seconds=60.0, mip_gap=0.0):
        n=len(self.c); m=len(self.rows)
        ri=[]; ci=[]; data=[]; lows=np.empty(m,dtype=float); highs=np.empty(m,dtype=float)
        for r,(co,lo,hi) in enumerate(self.rows):
            lows[r]=lo; highs[r]=hi
            for j,v in co.items():
                if abs(float(v))>1e-12:
                    ri.append(r); ci.append(j); data.append(float(v))
        A=csr_matrix((np.asarray(data,dtype=float),(np.asarray(ri,dtype=np.int32),np.asarray(ci,dtype=np.int32))),shape=(m,n))
        return milp(
            c=np.asarray(self.c,dtype=float), integrality=np.asarray(self.integrality),
            bounds=Bounds(np.asarray(self.lb),np.asarray(self.ub)),
            constraints=LinearConstraint(A,lows,highs),
            options={"time_limit":float(max(2.0,seconds)),"presolve":True,"mip_rel_gap":float(max(0.0,mip_gap))},
        )


def _v2564_choose_fixed_gaps(year, month, slots, gap_meta, seconds=5.0):
    """Choose the exact optional gaps before scheduling and distribute them across posts."""
    fixed=set()
    onko_gap_day=gap_meta.get("onko_gap_day")
    if onko_gap_day:
        for s in slots:
            if s.day==int(onko_gap_day) and s.department=="Onko RO centre" and not s.blocked:
                fixed.add(s.idx); break
    optional_counts={int(d):int(c) for d,c in (gap_meta.get("optional_gap_counts") or {}).items()}
    if not optional_counts:
        optional_counts={int(d):1 for d in (gap_meta.get("optional_gap_days") or [])}
    optional_days=set(optional_counts)
    if not optional_days:
        return fixed
    options=[s for s in slots if s.day in optional_days and not s.blocked and not s.mandatory and s.department!="Onko RO centre"]
    # V2.5.97: Mammography is the least-required cabinet. When optional capacity
    # must be left empty, consume Mammography gaps first; only then water-fill
    # unavoidable gaps across the remaining ordinary posts.
    def _gap_cost(sl):
        tiny=(((sl.day+1)*17+(sl.idx+1)*7)%53)*1e-5
        return (-1000.0 if rotation_category(sl)=="Mamografijos" else 0.0) + tiny
    mb=_V2564FastMB(); g={s.idx:mb.var(cost=_gap_cost(s)) for s in options}
    for d in sorted(optional_days):
        co={g[s.idx]:1.0 for s in options if s.day==d}
        need=int(optional_counts.get(d,1))
        if len(co)<need: return None
        mb.constraint(co,float(need),float(need))
    cats=sorted({rotation_category(s) for s in options if rotation_category(s)!="Mamografijos"})
    expr={cat:{g[s.idx]:1.0 for s in options if rotation_category(s)==cat} for cat in cats}
    for ai,c1 in enumerate(cats):
        for c2 in cats[ai+1:]:
            co=dict(expr[c1])
            for v,c in expr[c2].items(): co[v]=co.get(v,0.0)-c
            mb.constraint(co,-2.0,2.0)
    res=mb.solve(seconds)
    if res.x is None: return None
    fixed.update(sid for sid,v in g.items() if float(res.x[v])>0.5)
    return fixed


def _v2564_work_pattern(year, month, people, slots, targets, fixed_gaps, seconds=60.0, structural_relaxation=False, weekend_spread_cap=4):
    """Phase 1: choose dates/AM/PM/FULL without deciding weekday post labels.

    V2.5.107 keeps every `Negaliu dirbti` block mandatory. The normal pass uses
    the historical 0-1 structural corridors. If that pass cannot return a candidate,
    ``structural_relaxation=True`` converts selected fairness-only rules into
    high-priority minimax objectives, so fairness may worsen before any hard wish.
    Safety/rest, exact workload, coverage and Onko parity remain hard.
    """
    n=len(people); ndays=calendar.monthrange(year,month)[1]
    mb=_V2564FastMB(); am={}; pm={}; full={}; work={}; dbl={}; rh_by_person={pi:[] for pi in range(n)}
    # V2.5.71: workday-length preference redistributes a neutral, group-level
    # double pool. It must not manufacture extra AM+PM double-days.
    mixed_dev_vars={}
    # V2.5.96: no longitudinal fairness catch-up. Each month starts from a
    # clean water-fill baseline. Cross-month state is retained only for safety/spacing.
    prior_onko=[0.0 for _ in people]
    min_prior_onko=0.0
    onko_catchup_unit=0.0
    for pi,p in enumerate(people):
        onko_prior_penalty=max(0.0,prior_onko[pi]-min_prior_onko)*onko_catchup_unit
        for d in range(1,ndays+1):
            am[(pi,d)]=mb.var(cost=(((pi+1)*31+d*7)%97)*1e-7)
            pm[(pi,d)]=mb.var(cost=(((pi+1)*29+d*11)%89)*1e-7)
            full[(pi,d)]=mb.var(cost=onko_prior_penalty+(((pi+1)*23+d*13)%83)*1e-7)
            work[(pi,d)]=mb.var()
            # Neutral baseline cost only. Personal 6h/12h direction is added in a
            # second solve after the neutral total number of doubles is locked.
            dbl[(pi,d)]=mb.var(cost=3.0)
    # Coverage by time block; exact post labels are deferred to phase 2.
    for d in range(1,ndays+1):
        am_slots=[s for s in slots if s.day==d and not s.blocked and s.idx not in fixed_gaps and s.department!="Onko RO centre" and s.block=="AM"]
        pm_slots=[s for s in slots if s.day==d and not s.blocked and s.idx not in fixed_gaps and s.department!="Onko RO centre" and s.block=="PM"]
        full_slots=[s for s in slots if s.day==d and not s.blocked and s.idx not in fixed_gaps and s.department=="Onko RO centre"]
        mb.constraint({am[(pi,d)]:1.0 for pi in range(n)},len(am_slots),len(am_slots))
        mb.constraint({pm[(pi,d)]:1.0 for pi in range(n)},len(pm_slots),len(pm_slots))
        mb.constraint({full[(pi,d)]:1.0 for pi in range(n)},len(full_slots),len(full_slots))
    # Person-level feasibility and exact monthly workload.
    for pi,p in enumerate(people):
        for d in range(1,ndays+1):
            mb.constraint({am[(pi,d)]:1.0,full[(pi,d)]:1.0},-np.inf,1.0)
            mb.constraint({pm[(pi,d)]:1.0,full[(pi,d)]:1.0},-np.inf,1.0)
            # number of assignments = one worked day + one extra unit if a true AM+PM double
            mb.constraint({am[(pi,d)]:1.0,pm[(pi,d)]:1.0,full[(pi,d)]:1.0,work[(pi,d)]:-1.0,dbl[(pi,d)]:-1.0},0.0,0.0)
            mb.constraint({dbl[(pi,d)]:1.0,am[(pi,d)]:-1.0},-np.inf,0.0)
            mb.constraint({dbl[(pi,d)]:1.0,pm[(pi,d)]:-1.0},-np.inf,0.0)
            # V2.5.107 RESIDENT HARD is a real generation constraint. A resident
            # marked unavailable for a block cannot be assigned there for any reason;
            # lower structural fairness or SOFT wishes must adapt around this.
            if hard_unavailable_for_block(p,d,"AM") or any(rday==d and blocks_overlap(rblock,"AM") for rday,rblock in p.reserved_backup):
                mb.constraint({am[(pi,d)]:1.0},0.0,0.0)
            if hard_unavailable_for_block(p,d,"PM") or any(rday==d and blocks_overlap(rblock,"PM") for rday,rblock in p.reserved_backup):
                mb.constraint({pm[(pi,d)]:1.0},0.0,0.0)
            if hard_unavailable_for_block(p,d,"FULL") or any(rday==d and blocks_overlap(rblock,"FULL") for rday,rblock in p.reserved_backup):
                mb.constraint({full[(pi,d)]:1.0},0.0,0.0)
        co={}
        for d in range(1,ndays+1): co[am[(pi,d)]]=2.0; co[pm[(pi,d)]]=2.0; co[full[(pi,d)]]=3.0
        # V2.5.67 ABSOLUTE workload equality. x2 arithmetic keeps 1.5-unit Onko
        # integral, but no +/-0.5 escape is permitted.
        mb.constraint(co,targets[p.initials]*2,targets[p.initials]*2)
        # One Onko day = 1.5 units. Even individual counts keep an integer target
        # reachable: 0,2,4... Onko days only.
        k=mb.var(0,max(1,ndays//2),True)
        eco={k:-2.0}; eco.update({full[(pi,d)]:1.0 for d in range(1,ndays+1)})
        mb.constraint(eco,0.0,0.0)
        # V2.5.68 ABSOLUTE recovery rule: Onko RO is a 9h FULL day and may not
        # be followed by another Onko RO assignment on the next calendar day.
        # This is a hard feasibility rule, not a preference. It also crosses the
        # month boundary when the previous published SYSTEM month ended with Onko.
        if bool(getattr(p,"prior_last_day_onko",False)):
            mb.constraint({full[(pi,1)]:1.0},0.0,0.0)
        for d in range(1,ndays):
            mb.constraint({full[(pi,d)]:1.0,full[(pi,d+1)]:1.0},-np.inf,1.0)

        # V2.5.70/71 MIXED means a genuine mixture, not merely "no preference".
        # The deviation variables exist during the neutral solve with zero cost;
        # they become a small work-style objective only after total doubles lock.
        if max(0,min(3,int(getattr(p,"shift_length_preference",0) or 0)))==2:
            mix_pos=mb.var(0,ndays,False,cost=0.0)
            mix_neg=mb.var(0,ndays,False,cost=0.0)
            mixed_dev_vars[pi]=(mix_pos,mix_neg)
            mix_expr={mix_pos:-1.0,mix_neg:1.0}
            for d in range(1,ndays+1):
                mix_expr[dbl[(pi,d)]]=mix_expr.get(dbl[(pi,d)],0.0)+2.0
                mix_expr[work[(pi,d)]]=mix_expr.get(work[(pi,d)],0.0)-1.0
                mix_expr[full[(pi,d)]]=mix_expr.get(full[(pi,d)],0.0)+1.0
            mb.constraint(mix_expr,0.0,0.0)

    # V2.5.67 Onko monthly fairness: pair allocation permits a spread of 2, never
    # more. With 22 slots / 16 residents this naturally gives 11 residents x2 and
    # 5 residents x0. Prior published Onko counts above determine who catches up.
    for i in range(n):
        for j in range(i+1,n):
            co={}
            for d in range(1,ndays+1):
                co[full[(i,d)]]=1.0; co[full[(j,d)]]=co.get(full[(j,d)],0.0)-1.0
            mb.constraint(co,-2.0,2.0)
    # Double fairness is structural, but below mandatory cannot-work blocks.
    # Normal mode keeps the <=2 corridor. The zero-hard fallback minimizes the
    # actual double spread instead of making a hard wish infeasible.
    double_style_slacks=[]
    if not structural_relaxation:
        for i in range(n):
            for j in range(i+1,n):
                sv=mb.var(0.0,0.0,False,cost=0.15)
                double_style_slacks.append(sv)
                co={}
                for d in range(1,ndays+1):
                    co[dbl[(i,d)]]=1.0
                    co[dbl[(j,d)]]=co.get(dbl[(j,d)],0.0)-1.0
                co[sv]=co.get(sv,0.0)-1.0
                mb.constraint(co,-np.inf,float(DOUBLE_SPREAD_MAX))
                co2={v:-c for v,c in co.items() if v!=sv}; co2[sv]=-1.0
                mb.constraint(co2,-np.inf,float(DOUBLE_SPREAD_MAX))
    else:
        # Certified last-resort structural corridor used only after the strict
        # zero-hard pass returned no candidate. It is still bounded and remains
        # far above SOFT in the hierarchy; importantly it cannot buy a hard loss.
        for i in range(n):
            for j in range(i+1,n):
                co={}
                for d in range(1,ndays+1):
                    co[dbl[(i,d)]]=1.0
                    co[dbl[(j,d)]]=co.get(dbl[(j,d)],0.0)-1.0
                mb.constraint(co,-6.0,6.0)

    # V2.5.77 ABSOLUTE SYSTEM FRIDAY WATER-FILL.
    # Friday burden is a structural generation rule, just like the all-post
    # water-fill: every resident must receive the mathematical floor/ceil share
    # of ALL filled Friday assignments. Preferred/voluntary Friday requests do
    # not exempt a resident from the structural 0-1 corridor.
    friday_days=[d for d in range(1,ndays+1) if date(year,month,d).weekday()==4]
    total_friday_assignments=sum(
        1 for s in slots
        if s.day in friday_days and not s.blocked and s.idx not in fixed_gaps
    )
    friday_lo=total_friday_assignments//max(1,n)
    friday_hi=int(math.ceil(float(total_friday_assignments)/float(max(1,n))))
    _friday_expr=[]
    for pi,p in enumerate(people):
        co={}
        for d in friday_days:
            co[am[(pi,d)]]=co.get(am[(pi,d)],0.0)+1.0
            co[pm[(pi,d)]]=co.get(pm[(pi,d)],0.0)+1.0
            co[full[(pi,d)]]=co.get(full[(pi,d)],0.0)+1.0
        _friday_expr.append(co)
        if not structural_relaxation:
            mb.constraint(co,float(friday_lo),float(friday_hi))
    if structural_relaxation and _friday_expr:
        # September regression showed that strict 4-5 each can conflict with the
        # mandatory availability layer. Permit a bounded 2-unit entitlement
        # expansion before sacrificing any hard wish.
        for expr in _friday_expr:
            mb.constraint(expr,float(max(0,friday_lo-2)),float(friday_hi+2))

    # V2.5.97 mandatory backup-capacity reservation for the two-phase solver.
    # A required backup must be a distinct ABSOLUTE-HARD-safe resident who is free
    # for the covered time block. For Onko FULL this deliberately reserves one
    # completely work-free resident that day.
    _required_backup_slots=[sl for sl in slots if backup_required_slot(sl) and not sl.blocked and sl.idx not in fixed_gaps]
    _required_by_day_block={}
    for sl in _required_backup_slots:
        _required_by_day_block.setdefault((sl.day,sl.block),[]).append(sl)
    for (d,block),_rows in _required_by_day_block.items():
        candidates=[pi for pi,p in enumerate(people) if not hard_unavailable_for_block(p,d,block)]
        if not candidates:
            return None
        if block=="FULL":
            busy={work[(pi,d)]:1.0 for pi in candidates}
        elif block=="AM":
            busy={}
            for pi in candidates:
                busy[am[(pi,d)]]=busy.get(am[(pi,d)],0.0)+1.0
                busy[full[(pi,d)]]=busy.get(full[(pi,d)],0.0)+1.0
        else:
            busy={}
            for pi in candidates:
                busy[pm[(pi,d)]]=busy.get(pm[(pi,d)],0.0)+1.0
                busy[full[(pi,d)]]=busy.get(full[(pi,d)],0.0)+1.0
        mb.constraint(busy,-np.inf,float(len(candidates)-1))

    max_days7=min(int(rule_value("max_workdays_rolling7")),int(FATIGUE_MAX_WORKDAYS_ROLLING7))
    max_hours7=min(float(rule_value("max_hours_rolling7")),float(FATIGUE_ROLLING7_HARD_CEILING_HOURS))
    for pi,p in enumerate(people):
        for start in range(1,ndays-6+1):
            mb.constraint({work[(pi,d)]:1.0 for d in range(start,start+7)},-np.inf,float(max_days7))
            co={}
            for d in range(start,start+7): co[am[(pi,d)]]=6.0; co[pm[(pi,d)]]=6.0; co[full[(pi,d)]]=9.0
            mb.constraint(co,-np.inf,max_hours7)
        # Generator recovery rule: after two consecutive AM+PM doubles, next day is PM-only/off.
        for d in range(3,ndays+1):
            mb.constraint({dbl[(pi,d-2)]:1.0,dbl[(pi,d-1)]:1.0,am[(pi,d)]:1.0,full[(pi,d)]:1.0},-np.inf,2.0)
    # V2.5.90 BASELINE WEEKEND VOLUNTEERS.
    # Standard months keep the old exact raw floor/ceil weekend water-fill.
    # In the FIRST no-history month, explicit weekend "prefer to work" assignments
    # are removed from the fairness expression. The remaining NON-voluntary burden
    # is pairwise water-filled at spread <=1.
    weekend_days=[d for d in range(1,ndays+1) if date(year,month,d).weekday()>=5]
    total_weekend=sum(2 for _d in weekend_days)
    wlo=total_weekend//max(1,n); whi=int(math.ceil(total_weekend/max(1,n)))
    anchors=sorted({d if date(year,month,d).weekday()==5 else d-1 for d in weekend_days})

    # V2.5.104 PREFERENCE-AWARE WEEKEND WATER-FILL. Saturday and Sunday remain
    # separate burden classes, but an explicit month-specific/recurring
    # “Pageidauju dirbti” on a weekend is a voluntary burden choice. Volunteered
    # assignments are removed from the fairness burden expression; only the
    # REMAINING non-voluntary weekend load is water-filled at spread <=1.
    # This lets a resident receive several explicitly requested Sundays when other
    # residents are neutral / prefer not to work, without calling that willing load
    # an unfair SYSTEM burden. Raw exposure remains visible in statistics.
    saturday_days=[d for d in weekend_days if date(year,month,d).weekday()==5]
    sunday_days=[d for d in weekend_days if date(year,month,d).weekday()==6]

    def _weekend_volunteer_block(p,d,block):
        if d in p.preferred:
            return True
        if block=="AM" and d in p.preferred_am:
            return True
        if block=="PM" and d in p.preferred_pm:
            return True
        return False

    # V2.5.112 ADMIN RAW WEEKEND WATER-FILL. Weekend wishes are audit-only
    # during SYSTEM generation and never exempt raw Saturday/Sunday/weekend burden.
    baseline_weekend_volunteer_mode=False
    weekend_raw_expr={}
    weekend_vol_expr={}
    weekend_fair_expr={}
    weekend_vol_count={}
    active_weekend_volunteers=[]

    for pi,p in enumerate(people):
        raw={}
        vol={}
        for d in weekend_days:
            raw[am[(pi,d)]]=raw.get(am[(pi,d)],0.0)+1.0
            raw[pm[(pi,d)]]=raw.get(pm[(pi,d)],0.0)+1.0
            # Whole-day positive request is fulfilled by working that DAY at all,
            # therefore it contributes at most one voluntary fairness-exemption unit.
            if d in p.preferred:
                vol[work[(pi,d)]]=vol.get(work[(pi,d)],0.0)+1.0
            else:
                if d in p.preferred_am:
                    vol[am[(pi,d)]]=vol.get(am[(pi,d)],0.0)+1.0
                if d in p.preferred_pm:
                    vol[pm[(pi,d)]]=vol.get(pm[(pi,d)],0.0)+1.0
        weekend_raw_expr[pi]=raw
        weekend_vol_expr[pi]=vol
        fair=dict(raw)
        if baseline_weekend_volunteer_mode:
            for v,c in vol.items():
                fair[v]=fair.get(v,0.0)-c
        weekend_fair_expr[pi]=fair

        vc=mb.var(0,max(1,len(vol)),False,cost=0.0)
        weekend_vol_count[pi]=vc
        vco=dict(vol); vco[vc]=vco.get(vc,0.0)-1.0
        mb.constraint(vco,0.0,0.0)
        if baseline_weekend_volunteer_mode and vol:
            active_weekend_volunteers.append(pi)

    # Combined weekend burden: strict 0-1 in the normal pass; minimax structural
    # objective in the zero-hard fallback.
    _combined_weekend_expr=weekend_fair_expr if baseline_weekend_volunteer_mode else weekend_raw_expr
    if not structural_relaxation:
        if baseline_weekend_volunteer_mode:
            for i in range(n):
                for j in range(i+1,n):
                    co=dict(weekend_fair_expr[i])
                    for v,c in weekend_fair_expr[j].items():
                        co[v]=co.get(v,0.0)-c
                    mb.constraint(co,-1.0,1.0)
        else:
            for pi in range(n):
                mb.constraint(weekend_raw_expr[pi],wlo,whi)
    else:
        for i in range(n):
            for j in range(i+1,n):
                co=dict(_combined_weekend_expr[i])
                for v,c in _combined_weekend_expr[j].items():
                    co[v]=co.get(v,0.0)-c
                mb.constraint(co,-float(weekend_spread_cap),float(weekend_spread_cap))

    # Saturday and Sunday are independently water-filled using the same
    # volunteer-adjusted burden semantics.
    for _label,_days in (("Saturday",saturday_days),("Sunday",sunday_days)):
        _raw_by_pi={}; _fair_by_pi={}
        for pi,p in enumerate(people):
            _raw={}; _vol={}
            for d in _days:
                _raw[am[(pi,d)]]=_raw.get(am[(pi,d)],0.0)+1.0
                _raw[pm[(pi,d)]]=_raw.get(pm[(pi,d)],0.0)+1.0
                _raw[full[(pi,d)]]=_raw.get(full[(pi,d)],0.0)+1.0
                if d in p.preferred:
                    _vol[work[(pi,d)]]=_vol.get(work[(pi,d)],0.0)+1.0
                else:
                    if d in p.preferred_am:
                        _vol[am[(pi,d)]]=_vol.get(am[(pi,d)],0.0)+1.0
                    if d in p.preferred_pm:
                        _vol[pm[(pi,d)]]=_vol.get(pm[(pi,d)],0.0)+1.0
            _raw_by_pi[pi]=_raw
            _fair=dict(_raw)
            if baseline_weekend_volunteer_mode:
                for v,c in _vol.items():
                    _fair[v]=_fair.get(v,0.0)-c
            _fair_by_pi[pi]=_fair
        if not structural_relaxation:
            if baseline_weekend_volunteer_mode:
                for i in range(n):
                    for j in range(i+1,n):
                        _co=dict(_fair_by_pi[i])
                        for v,c in _fair_by_pi[j].items():
                            _co[v]=_co.get(v,0.0)-c
                        if _co:
                            mb.constraint(_co,-1.0,1.0)
            else:
                _total=2*len(_days)
                _lo=_total//max(1,n); _hi=int(math.ceil(float(_total)/float(max(1,n))))
                for pi in range(n):
                    if _raw_by_pi[pi]:
                        mb.constraint(_raw_by_pi[pi],float(_lo),float(_hi))
        else:
            _exprs=_fair_by_pi if baseline_weekend_volunteer_mode else _raw_by_pi
            for i in range(n):
                for j in range(i+1,n):
                    _co=dict(_exprs[i])
                    for v,c in _exprs[j].items():
                        _co[v]=_co.get(v,0.0)-c
                    if _co:
                        mb.constraint(_co,-float(weekend_spread_cap),float(weekend_spread_cap))

    # V2.5.102 PERSISTENT WORK-STYLE DIRECTION. These costs are applied in the
    # day-pattern phase, where weekend/weekday placement is still changeable.
    # Exact weekend “Pageidauju dirbti” wishes are handled above as voluntary
    # burden and may therefore widen RAW exposure while non-voluntary burden stays
    # water-filled. The persistent weekend-style slider remains a directional
    # SOFT tie-break inside the remaining feasible capacity.
    for pi,p in enumerate(people):
        # V2.5.112: residents cannot buy extra SYSTEM weekend exposure through
        # a long-term weekend preference. The setting is retained for audit/UI only.
        _we=0
        _wd=max(-2,min(2,int(getattr(p,"weekday_preference",0) or 0)))
        if _wd:
            _w=90.0*abs(_wd)
            for d in range(1,ndays+1):
                if date(year,month,d).weekday()<5:
                    mb.c[work[(pi,d)]] += (-_w if _wd>0 else _w)

    # Weekend-pair uniqueness is a strong fatigue/fairness preference, but V2.5.107
    # places it below mandatory `Negaliu dirbti`. The fallback allows extra weekend
    # assignments only through a very expensive explicit excess variable.
    weekend_pair_excess_vars=[]
    for pi,p in enumerate(people):
        for a in anchors:
            co={}
            for d in (a,a+1):
                if 1<=d<=ndays and date(year,month,d).weekday()>=5:
                    co[am[(pi,d)]]=co.get(am[(pi,d)],0.0)+1.0
                    co[pm[(pi,d)]]=co.get(pm[(pi,d)],0.0)+1.0
                    co[full[(pi,d)]]=co.get(full[(pi,d)],0.0)+1.0
            if not structural_relaxation:
                mb.constraint(co,-np.inf,1.0)
            else:
                # One additional assignment in a Sat+Sun pair is a bounded
                # structural concession, never a safety/HARD concession.
                mb.constraint(co,-np.inf,2.0)

    weekend_volunteer_waterfill=None
    if active_weekend_volunteers:
        max_req=max(len(weekend_vol_expr[pi]) for pi in active_weekend_volunteers)
        total_cap=sum(len(weekend_vol_expr[pi]) for pi in active_weekend_volunteers)
        wv_min=mb.var(0,max_req,False,cost=0.0)
        wv_max=mb.var(0,max_req,False,cost=0.0)
        wv_total=mb.var(0,total_cap,False,cost=0.0)
        total_co={wv_total:-1.0}
        for pi in active_weekend_volunteers:
            vc=weekend_vol_count[pi]
            mb.constraint({vc:1.0,wv_min:-1.0},0.0,np.inf)
            mb.constraint({vc:1.0,wv_max:-1.0},-np.inf,0.0)
            total_co[vc]=total_co.get(vc,0.0)+1.0
        mb.constraint(total_co,0.0,0.0)
        weekend_volunteer_waterfill={
            "active":active_weekend_volunteers,
            "min":wv_min,"max":wv_max,"total":wv_total,
            "total_cap":total_cap,"max_req":max_req,
        }
    # Resident-HARD: total losses first, then the maximum loss suffered by any one resident.
    def add_rh(pi,p,d,block):
        lv=mb.var(cost=1000000.0); rh_by_person[pi].append(lv)
        vals=[am[(pi,d)],pm[(pi,d)],full[(pi,d)]] if block is None else ([am[(pi,d)],full[(pi,d)]] if block=="AM" else [pm[(pi,d)],full[(pi,d)]])
        for v in vals: mb.constraint({v:1.0,lv:-1.0},-np.inf,0.0)
        co={lv:1.0}
        for v in vals: co[v]=co.get(v,0.0)-1.0
        mb.constraint(co,-np.inf,0.0)
    for pi,p in enumerate(people):
        for d in p.unavailable: add_rh(pi,p,d,None)
        for d in p.unavailable_am: add_rh(pi,p,d,"AM")
        for d in p.unavailable_pm: add_rh(pi,p,d,"PM")
    rhmax=mb.var(0,100,True,cost=10000.0)
    for pi in range(n):
        co={rhmax:-1.0}
        for lv in rh_by_person[pi]: co[lv]=1.0
        mb.constraint(co,-np.inf,0.0)
    # SOFT-1 (free time) outranks SOFT-2 (positive work request). Each resident's
    # raw request volume is normalized so submitting extra requests does not buy
    # proportionally more influence.
    def add_hit(pi,d,block,cost):
        hv=mb.var(cost=cost)
        vals=[am[(pi,d)],pm[(pi,d)],full[(pi,d)]] if block is None else ([am[(pi,d)],full[(pi,d)]] if block=="AM" else [pm[(pi,d)],full[(pi,d)]])
        for v in vals: mb.constraint({v:1.0,hv:-1.0},-np.inf,0.0)
        co={hv:1.0}
        for v in vals: co[v]=co.get(v,0.0)-1.0
        mb.constraint(co,-np.inf,0.0)
        return hv
    for pi,p in enumerate(people):
        nfree=len(p.soft_free)+len(p.soft_free_am)+len(p.soft_free_pm)
        npref=len(p.preferred)+len(p.preferred_am)+len(p.preferred_pm)
        free_w=5000.0/max(1,nfree); pref_w=2000.0/max(1,npref)
        for d in p.soft_free:
            if date(year,month,d).weekday()<5: add_hit(pi,d,None,+free_w)
        for d in p.soft_free_am:
            if date(year,month,d).weekday()<5: add_hit(pi,d,"AM",+free_w)
        for d in p.soft_free_pm:
            if date(year,month,d).weekday()<5: add_hit(pi,d,"PM",+free_w)
        for d in p.preferred:
            if date(year,month,d).weekday()<5: add_hit(pi,d,None,-pref_w)
        for d in p.preferred_am:
            if date(year,month,d).weekday()<5: add_hit(pi,d,"AM",-pref_w)
        for d in p.preferred_pm:
            if date(year,month,d).weekday()<5: add_hit(pi,d,"PM",-pref_w)
    # Internal high-priority co-location target: maximize distinct calendar weeks
    # with one shared CENTRO RO AM/PM block, capped monthly. This is deliberately
    # outside resident request/satisfaction accounting.
    priority_colocation_week_vars=[]
    priority_colocation_block_vars={}
    _priority_idx=[]
    _ini_to_pi={p.initials:pi for pi,p in enumerate(people)}
    if all(ini in _ini_to_pi for ini in _PRIORITY_COLOCATION_GROUP):
        _priority_idx=[_ini_to_pi[ini] for ini in _PRIORITY_COLOCATION_GROUP]
        _by_week={}
        for d in range(1,ndays+1):
            dt=date(year,month,d)
            wk=dt-timedelta(days=dt.weekday())
            for block in ("AM","PM"):
                centro_rows=[sl for sl in slots if sl.day==d and sl.block==block and not sl.blocked and sl.idx not in fixed_gaps and sl.department.startswith("CENTRO RO ")]
                if len(centro_rows)<len(_priority_idx):
                    continue
                cv=mb.var(0.0,1.0,True,cost=0.0)
                priority_colocation_block_vars[(d,block)]=cv
                for pi in _priority_idx:
                    av=am[(pi,d)] if block=="AM" else pm[(pi,d)]
                    mb.constraint({cv:1.0,av:-1.0},-np.inf,0.0)
                _by_week.setdefault(wk,[]).append(cv)
        for wk,cvars in sorted(_by_week.items()):
            wv=mb.var(0.0,1.0,True,cost=0.0)
            priority_colocation_week_vars.append(wv)
            co={wv:-1.0}
            for cv in cvars:
                co[cv]=co.get(cv,0.0)+1.0
                mb.constraint({cv:1.0,wv:-1.0},-np.inf,0.0)
            mb.constraint(co,0.0,np.inf)
            mb.constraint({cv:1.0 for cv in cvars},-np.inf,1.0)
        if priority_colocation_week_vars:
            mb.constraint({wv:1.0 for wv in priority_colocation_week_vars},-np.inf,float(_PRIORITY_COLOCATION_MAX_PER_MONTH))

    # V2.5.106 SINGLE-PASS WORK-PATTERN SOLVE.
    #
    # V2.5.105 staged the same large MILP through several consecutive solves
    # (Resident-HARD proof -> volunteer weekend lock -> neutral solve -> work-style
    # redistribution). On the real September request set the very first 6-second
    # Resident-HARD-only pass can time out with no incumbent, even though the full
    # model is feasible. A no-incumbent timeout must not block generation.
    #
    # V2.5.106 expresses the same priority order in one lexicographically scaled
    # objective and solves the work-pattern model once. Resident-HARD remains far
    # above volunteer/soft/work-style preferences. Work-style is a small tie-breaker
    # on the neutral double cost, so a 12h preference cannot manufacture an extra
    # double merely to gain preference score.
    single_costs=list(mb.c)
    weekend_volunteer_locks={}

    # V2.5.107 constitution: Resident-HARD is not an objective weight.
    # Every `Negaliu dirbti` block is encoded as a real assignment prohibition
    # and the audit-loss ledger is separately hard-locked to zero below. The
    # remaining objective therefore starts with voluntary/weekend structure and
    # ordinary SOFT inside the already zero-loss feasible space.

    if weekend_volunteer_waterfill is not None:
        wv=weekend_volunteer_waterfill
        # Max-min volunteer fulfillment first, then total fulfillment, with max as
        # a tiny anti-skew tie-breaker. These weights are intentionally below the
        # Resident-HARD tiers and above ordinary SOFT scores.
        single_costs[wv["min"]]-=1000000.0
        single_costs[wv["total"]]-=100000.0
        single_costs[wv["max"]]+=1000.0

    for wv in priority_colocation_week_vars:
        single_costs[wv]-=10000.0

    workstyle_applied=False
    pref12_indices=[]
    pref6_indices=[]
    _STYLE_UNIT=0.50
    for pi,p in enumerate(people):
        shift_len=max(0,min(3,int(getattr(p,"shift_length_preference",0) or 0)))
        if shift_len==0 and bool(getattr(p,"avoid_doubles",False)):
            shift_len=1
        if shift_len==1:
            workstyle_applied=True
            pref6_indices.append(pi)
            for d in range(1,ndays+1):
                single_costs[dbl[(pi,d)]] += _STYLE_UNIT
        elif shift_len==3:
            workstyle_applied=True
            pref12_indices.append(pi)
            for d in range(1,ndays+1):
                # Base neutral double cost is +3.0, so -0.5 can redistribute an
                # already-needed double but cannot make an extra double profitable.
                single_costs[dbl[(pi,d)]] -= _STYLE_UNIT
        elif shift_len==2:
            workstyle_applied=True
            if pi in mixed_dev_vars:
                a,b=mixed_dev_vars[pi]
                single_costs[a]+=_STYLE_UNIT
                single_costs[b]+=_STYLE_UNIT

    # Active work-style may widen the neutral double spread, as in V2.5.97, but
    # only through explicit penalized slack and never through a second blocking solve.
    if workstyle_applied:
        for sv in double_style_slacks:
            mb.ub[sv]=float(ndays)

    _exact_soft_lock_mark=None
    _workstyle_lock_mark=None
    if structural_relaxation:
        # V2.5.107 RESILIENT ZERO-HARD FALLBACK.
        #
        # The strict 0-1 structural pattern can be mathematically infeasible once
        # all mandatory `Negaliu dirbti` blocks are respected. In that case we do
        # NOT launch another slow weighted-optimum solve. Instead we ask a sequence
        # of bounded FEASIBILITY questions:
        #   1) zero HARD + every exact date/block SOFT wish + work-style target;
        #   2) if needed, zero HARD + every exact date/block SOFT wish;
        #   3) if needed, zero HARD only.
        # This preserves the vertical hierarchy and returns the highest fully
        # feasible wish tier found without allowing a secondary objective to stall
        # a valid draft. The generated audit explicitly shows anything left unmet.
        _exact_soft_lock_mark=len(mb.rows)
        for pi,p in enumerate(people):
            full_free=set(p.soft_free)
            for d in sorted(full_free):
                if date(year,month,d).weekday()<5:
                    mb.constraint({work[(pi,d)]:1.0},0.0,0.0)
            for d in sorted(set(p.soft_free_am)-full_free):
                if date(year,month,d).weekday()<5:
                    mb.constraint({am[(pi,d)]:1.0,full[(pi,d)]:1.0},0.0,0.0)
            for d in sorted(set(p.soft_free_pm)-full_free):
                if date(year,month,d).weekday()<5:
                    mb.constraint({pm[(pi,d)]:1.0,full[(pi,d)]:1.0},0.0,0.0)
            full_pref=set(p.preferred)
            for d in sorted(full_pref):
                if date(year,month,d).weekday()<5:
                    mb.constraint({work[(pi,d)]:1.0},1.0,1.0)
            for d in sorted(set(p.preferred_am)-full_pref):
                if date(year,month,d).weekday()<5:
                    mb.constraint({am[(pi,d)]:1.0,full[(pi,d)]:1.0},1.0,1.0)
            for d in sorted(set(p.preferred_pm)-full_pref):
                if date(year,month,d).weekday()<5:
                    mb.constraint({pm[(pi,d)]:1.0,full[(pi,d)]:1.0},1.0,1.0)

        _workstyle_lock_mark=len(mb.rows)
        for pi,p in enumerate(people):
            _style=max(0,min(3,int(getattr(p,"shift_length_preference",0) or 0)))
            if _style==3:
                # Strong 12 h preference. This is a temporary SOFT feasibility
                # target, never a mandatory rule; if it conflicts with exact wishes
                # the engine drops only this work-style layer first.
                _prefer12_floor=max(1,int(math.floor(float(targets[p.initials])*0.36)))
                mb.constraint({dbl[(pi,d)]:1.0 for d in range(1,ndays+1)},float(_prefer12_floor),np.inf)
            elif _style==1 or (_style==0 and bool(getattr(p,"avoid_doubles",False))):
                _prefer6_cap=max(1,int(math.ceil(float(targets[p.initials])*0.24)))
                mb.constraint({dbl[(pi,d)]:1.0 for d in range(1,ndays+1)},-np.inf,float(_prefer6_cap))
            elif _style==2 and pi in mixed_dev_vars:
                # MIXED means a genuine near-even 6 h / 12 h blend. One-day
                # difference is the mathematical near-half outcome when the number
                # of normal workdays is odd.
                _mp,_mn=mixed_dev_vars[pi]
                mb.constraint({_mp:1.0},-np.inf,1.0)
                mb.constraint({_mn:1.0},-np.inf,1.0)

        # Pure feasibility objective: once a valid candidate exists, HiGHS may stop
        # instead of spending minutes proving a cosmetic weighted optimum. Tiny
        # deterministic tie-breaks keep repeated runs stable.
        mb.c=[0.0 for _ in mb.c]
        for (pi,d),v in am.items(): mb.c[v]+=(((pi+1)*31+d*7)%97)*1e-8
        for (pi,d),v in pm.items(): mb.c[v]+=(((pi+1)*29+d*11)%89)*1e-8
        for (pi,d),v in full.items(): mb.c[v]+=(((pi+1)*23+d*13)%83)*1e-8
        # Dream Team is an administrator rule above ordinary SOFT. Maximize the
        # number of represented weeks with a common SP+GE+ŠR work block inside
        # the already-fixed weekend water-fill corridor.
        for wv in priority_colocation_week_vars:
            mb.c[wv]-=1000.0
    else:
        mb.c=single_costs

    # V2.5.107 ZERO-LOSS RESIDENT-HARD GATE.
    # `Negaliu dirbti` is already encoded above as a hard assignment prohibition.
    # The request-loss variables are retained only for audit/backward compatibility
    # and must all evaluate to zero. There is no widening corridor and no trade
    # against fairness or SOFT satisfaction.
    _rh_loss_vars=[lv for vals in rh_by_person.values() for lv in vals]
    if _rh_loss_vars:
        mb.constraint({lv:1.0 for lv in _rh_loss_vars},0.0,0.0)
    _fallback_mode="WEIGHTED_STRICT"
    _bounded=max(12.0,min(float(seconds),18.0)) if structural_relaxation else max(12.0,float(seconds))
    res=mb.solve(_bounded)
    if res.x is not None and structural_relaxation:
        _fallback_mode="ALL_EXACT_PLUS_WORKSTYLE_FEASIBLE"
    if res.x is None and structural_relaxation and _workstyle_lock_mark is not None:
        # Drop only work-style shaping first; preserve every exact date/block wish.
        del mb.rows[_workstyle_lock_mark:]
        if _rh_loss_vars:
            mb.constraint({lv:1.0 for lv in _rh_loss_vars},0.0,0.0)
        res=mb.solve(_bounded)
        if res.x is not None:
            _fallback_mode="ALL_EXACT_WISHES_FEASIBLE_WORKSTYLE_RELAXED"
    if res.x is None and structural_relaxation and _exact_soft_lock_mark is not None:
        # Exact wishes are SOFT and can conflict with one another. Remove them only
        # after the stronger exact-wish pass failed, but keep every HARD block.
        del mb.rows[_exact_soft_lock_mark:]
        if _rh_loss_vars:
            mb.constraint({lv:1.0 for lv in _rh_loss_vars},0.0,0.0)
        res=mb.solve(_bounded)
        if res.x is not None:
            _fallback_mode="MANDATORY_ZERO_HARD_BASELINE_ONLY"
    if res.x is None:
        return None
    _rh_minimum_proven=True
    _rh_min_total_cap=0

    # The final single-pass solution itself defines the fixed group double pool.
    neutral_total_doubles=int(round(sum(float(res.x[dbl[(pi,d)]]) for pi in range(n) for d in range(1,ndays+1))))

    if weekend_volunteer_waterfill is not None:
        wv=weekend_volunteer_waterfill
        weekend_volunteer_locks={
            "min":round(max(0.0,float(res.x[wv["min"]])),6),
            "total":round(max(0.0,float(res.x[wv["total"]])),6),
            "max":round(max(0.0,float(res.x[wv["max"]])),6),
            "active":len(wv["active"]),
            "requested_assignment_slots":int(wv["total_cap"]),
            "mode":"V25106_SINGLE_PASS_WEIGHTED",
        }

    pattern={"am":{},"pm":{},"full":{}}
    for pi in range(n):
        for d in range(1,ndays+1):
            pattern["am"][(pi,d)]=float(res.x[am[(pi,d)]])>0.5
            pattern["pm"][(pi,d)]=float(res.x[pm[(pi,d)]])>0.5
            pattern["full"][(pi,d)]=float(res.x[full[(pi,d)]])>0.5
    pattern["resident_hard_min_total"]=int(round(sum(float(res.x[v]) for vals in rh_by_person.values() for v in vals)))
    pattern["structural_relaxation_mode"]=bool(structural_relaxation)
    pattern["weekend_spread_cap"]=int(1 if not structural_relaxation else weekend_spread_cap)
    pattern["zero_hard_fallback_wish_mode"]=_fallback_mode
    pattern["resident_hard_max_loss"]=int(round(float(res.x[rhmax])))
    pattern["resident_hard_minimum_proven"]=bool(_rh_minimum_proven)
    pattern["resident_hard_verified_min_total_cap"]=int(_rh_min_total_cap)
    pattern["objective_value"]=float(getattr(res,"fun",0.0) or 0.0)
    pattern["baseline_weekend_volunteer_mode"]=bool(baseline_weekend_volunteer_mode)
    pattern["baseline_weekend_volunteers"]=[people[pi].initials for pi in active_weekend_volunteers]
    pattern["baseline_weekend_volunteer_locks"]=dict(weekend_volunteer_locks)
    pattern["weekend_volunteer_counts"]={
        people[pi].initials:int(round(float(res.x[weekend_vol_count[pi]])))
        for pi in range(n)
    }
    pattern["weekend_raw_counts"]={
        people[pi].initials:int(round(sum(float(res.x[v])*c for v,c in weekend_raw_expr[pi].items())))
        for pi in range(n)
    }
    pattern["weekend_fair_counts"]={
        people[pi].initials:int(round(sum(float(res.x[v])*c for v,c in weekend_fair_expr[pi].items())))
        for pi in range(n)
    }
    pattern["neutral_total_doubles_lock"]=int(neutral_total_doubles)
    dvals=[]
    for pi in range(n):
        dvals.append(int(round(sum(float(res.x[dbl[(pi,d)]]) for d in range(1,ndays+1)))))
    pattern["double_counts"]={people[pi].initials:dvals[pi] for pi in range(n)}
    pattern["double_spread"]=int(max(dvals)-min(dvals)) if dvals else 0
    pref12_vals=[dvals[pi] for pi in pref12_indices]
    pattern["prefer12_people"]=[people[pi].initials for pi in pref12_indices]
    pattern["prefer12_cohort_size"]=len(pref12_indices)
    pattern["prefer12_cohort_min"]=min(pref12_vals) if pref12_vals else None
    pattern["prefer12_cohort_max"]=max(pref12_vals) if pref12_vals else None
    pattern["workstyle_style_solve_proven"]=bool(
        int(getattr(res,"status",1))==0
    )
    fvals=[]
    friday_days=[d for d in range(1,ndays+1) if date(year,month,d).weekday()==4]
    for pi in range(n):
        fvals.append(int(round(sum(
            float(res.x[am[(pi,d)]])+float(res.x[pm[(pi,d)]])+float(res.x[full[(pi,d)]])
            for d in friday_days
        ))))
    pattern["friday_counts"]={people[pi].initials:fvals[pi] for pi in range(n)}
    pattern["friday_spread"]=int(max(fvals)-min(fvals)) if fvals else 0
    pattern["friday_floor"]=int(min(fvals)) if fvals else 0
    pattern["friday_ceil"]=int(max(fvals)) if fvals else 0
    return pattern


def _v2564_assign_posts(year, month, people, slots, pattern, fixed_gaps, seconds=45.0):
    """Phase 2: label fixed work blocks with posts using structural all-post water-filling.

    V2.5.74 constitution:
      * work DATES/BLOCKS from phase 1 stay frozen;
      * exact post labels are solved jointly across all residents and all posts;
      * SPS RO/SPS UG target raw spread <=1;
      * every ordinary post except Onko first attempts the mathematically tight
        floor/ceil entitlement corridor (raw spread <=1);
      * a wider ordinary corridor is tried ONLY after the tighter one is proven
        infeasible, never because of a timeout;
      * within any unavoidable wider corridor, the objective minimizes total
        absolute distance from each post's equal-share entitlement, so 3/3/3/1/1/1
        is driven toward 2/2/2/2/2/2 whenever compatible post exchanges/cycles exist;
      * because all post labels are solved simultaneously, two-way, three-way and
        larger same-block redistribution cycles are handled automatically.

    Onko is excluded here because phase 1 already enforces its separate ABSOLUTE
    parity model: 0/2/4/... per resident and monthly spread <=2.
    """
    n=len(people); ndays=calendar.monthrange(year,month)[1]
    normal=[s for s in slots if not s.blocked and s.idx not in fixed_gaps and s.department!="Onko RO centre"]
    byid={s.idx:s for s in normal}

    baseline_weekend_volunteer_mode=bool(pattern.get("baseline_weekend_volunteer_mode",False))
    # V2.5.104: Onko-zero residents get first-exposure priority for Mammography.
    # Mammography remains the LAST optional cabinet at the gap-selection layer;
    # this rule only decides who should receive the Mammography slots that remain
    # after that low-priority cabinet volume is fixed. Structural post corridors
    # still dominate, so the preference cannot worsen a proven post-spread cap.
    _onko_zero_indices=[
        pi for pi in range(n)
        if not any(bool(pattern["full"][(pi,d)]) for d in range(1,ndays+1))
    ]
    _priority_idx=[]
    _ini_to_pi={p.initials:pi for pi,p in enumerate(people)}
    if all(ini in _ini_to_pi for ini in _PRIORITY_COLOCATION_GROUP):
        _priority_idx=[_ini_to_pi[ini] for ini in _PRIORITY_COLOCATION_GROUP]
    _priority_candidates_by_week={}
    if _priority_idx:
        for d in range(1,ndays+1):
            dt=date(year,month,d); wk=dt-timedelta(days=dt.weekday())
            for block in ("AM","PM"):
                if not all(bool(pattern[block.lower()][(pi,d)]) for pi in _priority_idx):
                    continue
                centro_rows=[sl for sl in normal if sl.day==d and sl.block==block and sl.department.startswith("CENTRO RO ")]
                if len(centro_rows)>=len(_priority_idx):
                    _priority_candidates_by_week.setdefault(wk,[]).append((d,block))

    volunteer_weekend_sps_const={}
    for pi,p in enumerate(people):
        c=0
        if baseline_weekend_volunteer_mode:
            weekend_days=sorted({s.day for s in normal if s.weekday>=5 and rotation_category(s)=="SPS RO"})
            for d in weekend_days:
                if d in p.preferred:
                    if bool(pattern["am"][(pi,d)] or pattern["pm"][(pi,d)]):
                        c+=1
                else:
                    if d in p.preferred_am and pattern["am"][(pi,d)]:
                        c+=1
                    if d in p.preferred_pm and pattern["pm"][(pi,d)]:
                        c+=1
        volunteer_weekend_sps_const[pi]=int(c)

    def attempt(critical_cap, noncritical_cap, attempt_seconds):
        mb=_V2564FastMB(); x={}
        for s in normal:
            for pi in range(n):
                works=pattern["am"][(pi,s.day)] if s.block=="AM" else pattern["pm"][(pi,s.day)]
                if works:
                    # V2.5.96: no longitudinal post catch-up/tie-break. Each month
                    # is solved from an equal current-month baseline.
                    base_cost=(((pi+1)*37+(s.idx+1)*13)%101)*1e-8
                    is_double_day=bool(pattern["am"][(pi,s.day)] and pattern["pm"][(pi,s.day)])
                    if is_double_day:
                        if rotation_category(s) in ("SPS RO","SPS UG"):
                            base_cost-=0.08
                        else:
                            base_cost+=0.01
                    if pi in _onko_zero_indices and rotation_category(s)=="Mamografijos":
                        base_cost-=0.25
                    x[(pi,s.idx)]=mb.var(cost=base_cost)

        # Every open normal post is filled exactly once.
        for s in normal:
            co={v:1.0 for (pi,sid),v in x.items() if sid==s.idx}
            mb.constraint(co,1.0,1.0)

        # Preserve each resident's phase-1 AM/PM work pattern exactly. The solver can
        # change only WHICH post a resident occupies inside an already-worked block.
        for pi in range(n):
            for d in range(1,ndays+1):
                for block in ("AM","PM"):
                    need=1.0 if (pattern["am"][(pi,d)] if block=="AM" else pattern["pm"][(pi,d)]) else 0.0
                    co={v:1.0 for (ppi,sid),v in x.items() if ppi==pi and byid[sid].day==d and byid[sid].block==block}
                    mb.constraint(co,need,need)
                if pattern["am"][(pi,d)] and pattern["pm"][(pi,d)]:
                    crit={v:1.0 for (ppi,sid),v in x.items() if ppi==pi and byid[sid].day==d and rotation_category(byid[sid]) in ("SPS RO","SPS UG")}
                    if crit:
                        hit=mb.var(0.0,1.0,False,cost=-0.30)
                        co=dict(crit); co[hit]=-1.0
                        mb.constraint(co,0.0,np.inf)

        # V2.5.105: the private high-priority co-location request is optimized
        # JOINTLY with post feasibility instead of being hard-materialized before
        # post water-fill. This implements the intended MAX 4 -> else 3 -> else 2
        # semantics. A candidate week counts only when all three residents are
        # actually placed in CENTRO RO in the same AM/PM block. Post water-fill and
        # HARD feasibility remain constraints, so an impossible fourth co-location
        # automatically falls back to the maximum feasible lower count instead of
        # making the whole post model infeasible.
        _coloc_week_vars=[]
        for wk,cands in sorted(_priority_candidates_by_week.items()):
            _cvars=[]
            for d,block in sorted(cands,key=lambda z:(z[0],0 if z[1]=="AM" else 1)):
                cv=mb.var(0.0,1.0,True,cost=0.0)
                _cvars.append(cv)
                for pi in _priority_idx:
                    centro_vars={v:1.0 for (ppi,sid),v in x.items()
                                 if ppi==pi and byid[sid].day==d and byid[sid].block==block
                                 and byid[sid].department.startswith("CENTRO RO ")}
                    if not centro_vars:
                        mb.constraint({cv:1.0},0.0,0.0)
                        continue
                    co={cv:1.0}
                    for v in centro_vars: co[v]=co.get(v,0.0)-1.0
                    mb.constraint(co,-np.inf,0.0)
            if _cvars:
                wv=mb.var(0.0,1.0,True,cost=-1000000.0)
                _coloc_week_vars.append(wv)
                for cv in _cvars:
                    mb.constraint({cv:1.0,wv:-1.0},-np.inf,0.0)
                co={wv:1.0}
                for cv in _cvars: co[cv]=co.get(cv,0.0)-1.0
                mb.constraint(co,-np.inf,0.0)
                mb.constraint({cv:1.0 for cv in _cvars},-np.inf,1.0)
        if _coloc_week_vars:
            mb.constraint({wv:1.0 for wv in _coloc_week_vars},-np.inf,float(_PRIORITY_COLOCATION_MAX_PER_MONTH))

        cats=[c for c in ROTATION_CATEGORIES if c!="Onko RO"]
        expr={}
        for pi in range(n):
            for cat in cats:
                expr[(pi,cat)]={v:1.0 for (ppi,sid),v in x.items() if ppi==pi and rotation_category(byid[sid])==cat}

        cat_slot_counts={cat:sum(1 for ss in normal if rotation_category(ss)==cat) for cat in cats}

        # Strong first-exposure bonus: if a resident has zero Onko RO this month,
        # maximize the number of such residents who receive at least one remaining
        # Mammography assignment. This is a tie-break/priority inside the already
        # proven structural post corridor, never a reason to widen it.
        _mammo_total=int(cat_slot_counts.get("Mamografijos",0) or 0)
        if _mammo_total>0:
            for pi in _onko_zero_indices:
                _mexpr=expr.get((pi,"Mamografijos"),{})
                if not _mexpr:
                    continue
                _seen=mb.var(0.0,1.0,True,cost=-2000.0)
                _lo_co=dict(_mexpr); _lo_co[_seen]=_lo_co.get(_seen,0.0)-1.0
                mb.constraint(_lo_co,0.0,np.inf)
                _hi_co=dict(_mexpr); _hi_co[_seen]=_hi_co.get(_seen,0.0)-float(_mammo_total)
                mb.constraint(_hi_co,-np.inf,0.0)

        for cat in cats:
            total=int(cat_slot_counts.get(cat,0))
            if total<=0:
                continue
            cap=critical_cap if cat in CRITICAL_ROTATION_CATEGORIES else noncritical_cap

            # In baseline volunteer mode, weekend SPS-RO assignments that were
            # explicitly volunteered are constants fixed by phase 1. Fairness is
            # applied to RAW_SPS_RO - VOLUNTARY_WEEKEND_SPS_RO.
            adjusted_sps=(baseline_weekend_volunteer_mode and cat=="SPS RO")
            if adjusted_sps:
                volunteer_total=sum(volunteer_weekend_sps_const.values())
                fair_total=max(0,total-volunteer_total)
                equal_share=float(fair_total)/float(max(1,n))
                lo=fair_total//max(1,n)
                hi=int(math.ceil(equal_share))
            else:
                equal_share=float(total)/float(max(1,n))
                lo=total//max(1,n)
                hi=int(math.ceil(equal_share))

            if int(cap)<=1:
                for pi in range(n):
                    offset=volunteer_weekend_sps_const.get(pi,0) if adjusted_sps else 0
                    mb.constraint(expr[(pi,cat)],float(lo+offset),float(hi+offset))
            else:
                cat_hi=max(1,total)
                vmax=mb.var(0,cat_hi,False,cost=20000.0)
                vmin=mb.var(0,cat_hi,False,cost=-20000.0)
                for pi in range(n):
                    offset=float(volunteer_weekend_sps_const.get(pi,0) if adjusted_sps else 0)
                    co_hi=dict(expr[(pi,cat)]); co_hi[vmax]=co_hi.get(vmax,0.0)-1.0
                    mb.constraint(co_hi,-np.inf,offset)
                    co_lo=dict(expr[(pi,cat)]); co_lo[vmin]=co_lo.get(vmin,0.0)-1.0
                    mb.constraint(co_lo,offset,np.inf)
                mb.constraint({vmax:1.0,vmin:-1.0},-np.inf,float(cap))

            # L1 distance from the FAIR entitlement. For adjusted SPS RO the raw
            # count is shifted by the resident's fixed volunteered weekend count.
            for pi in range(n):
                offset=float(volunteer_weekend_sps_const.get(pi,0) if adjusted_sps else 0)
                dev=mb.var(0.0,max(1.0,float(total)),False,cost=500.0)
                co1=dict(expr[(pi,cat)]); co1[dev]=co1.get(dev,0.0)-1.0
                mb.constraint(co1,-np.inf,equal_share+offset)
                co2={k:-v for k,v in expr[(pi,cat)].items()}; co2[dev]=co2.get(dev,0.0)-1.0
                mb.constraint(co2,-np.inf,-equal_share-offset)

        res=mb.solve(attempt_seconds)
        if res.x is None:
            return None,res

        assignments={}
        onko_by_day={s.day:s for s in slots if s.department=="Onko RO centre" and not s.blocked and s.idx not in fixed_gaps}
        for pi,p in enumerate(people):
            for d in range(1,ndays+1):
                if pattern["full"][(pi,d)]:
                    os=onko_by_day.get(d)
                    if os is None: return None,res
                    assignments[os.idx]=p.initials
        for (pi,sid),v in x.items():
            if float(res.x[v])>0.5:
                assignments[sid]=people[pi].initials
        return assignments,res

    # Never widen because of a timeout. 0-1 is the constitutional target for all
    # ordinary posts. Wider levels are allowed only after the tighter model is
    # mathematically proven infeasible by HiGHS.
    trials=[(1,1),(1,2),(1,3),(2,3)]
    logs=[]
    # V2.5.105: `seconds` is a TOTAL phase budget, not a per-corridor budget.
    # The old loop could spend up to 4× the advertised time and push Streamlit
    # generation into the legacy rescue path. Most feasible months solve in the
    # first 0-1 corridor, so give each trial a bounded slice and fail closed on an
    # unknown/timeout result instead of silently widening fairness.
    per_trial=max(4.0,float(seconds)/float(max(1,len(trials))))
    for cc,nc in trials:
        assignments,res=attempt(cc,nc,per_trial)
        logs.append({
            "critical_cap":cc,"noncritical_cap":nc,
            "status":int(getattr(res,"status",99)),"incumbent":bool(assignments),
            "meaning":"ORDINARY_WATERFILL_0_1" if nc==1 else f"PROVEN_WIDER_0_{nc}",
        })
        if assignments is not None:
            return assignments,cc,nc,logs,float(getattr(res,"fun",0.0) or 0.0)
        if int(getattr(res,"status",99))!=2:
            # timeout/no incumbent is NOT proof the tight water-fill corridor is impossible
            return None,None,None,logs,None
    return None,None,None,logs,None



def _v25105_assign_posts_resilient(year, month, people, slots, pattern, fixed_gaps, seconds=45.0):
    """Bounded post-label solver used by V2.5.105 production generation.

    The prior post solver mixed structural feasibility with many deviation auxiliaries.
    On some valid phase-1 work patterns HiGHS could spend a very long time proving a
    tight corridor, pushing the app into the legacy rescue model. This formulation
    keeps the same structural contract but is deliberately smaller:
      * fixed phase-1 AM/PM/FULL blocks are preserved exactly;
      * every open post is filled once;
      * SPS RO/SPS UG and ordinary post water-fill are tried in the same ascending
        certified corridors;
      * weekend-volunteered SPS RO exposure is offset from the fairness burden;
      * SP+GE+ŠR CENTRO RO co-location is maximized across every represented week;
        if all weeks cannot coexist with higher HARD/critical fairness, the engine
        returns the largest feasible weekly count and reports it explicitly;
      * Onko-zero residents are preferentially given at least one of the remaining
        Mammography assignments.

    No HARD or water-fill rule is relaxed merely because of a timeout. If the tight
    corridor returns an unknown/time-limit result with no incumbent, the function
    returns no schedule rather than silently widening it.
    """
    n=len(people); ndays=calendar.monthrange(year,month)[1]
    normal=[s for s in slots if not s.blocked and s.idx not in fixed_gaps and s.department!="Onko RO centre"]
    byid={s.idx:s for s in normal}
    baseline_weekend_volunteer_mode=bool(pattern.get("baseline_weekend_volunteer_mode",False))

    volunteer_weekend_sps_const={}
    for pi,p in enumerate(people):
        c=0
        if baseline_weekend_volunteer_mode:
            for d in sorted({s.day for s in normal if s.weekday>=5 and rotation_category(s)=="SPS RO"}):
                if d in p.preferred:
                    if bool(pattern["am"][(pi,d)] or pattern["pm"][(pi,d)]): c+=1
                else:
                    if d in p.preferred_am and pattern["am"][(pi,d)]: c+=1
                    if d in p.preferred_pm and pattern["pm"][(pi,d)]: c+=1
        volunteer_weekend_sps_const[pi]=int(c)

    _onko_zero_indices=[pi for pi in range(n) if not any(bool(pattern["full"][(pi,d)]) for d in range(1,ndays+1))]
    _ini_to_pi={p.initials:pi for pi,p in enumerate(people)}
    _priority_idx=[_ini_to_pi[i] for i in _PRIORITY_COLOCATION_GROUP if i in _ini_to_pi]
    if len(_priority_idx)!=len(_PRIORITY_COLOCATION_GROUP): _priority_idx=[]
    _priority_candidates_by_week={}
    if _priority_idx:
        for d in range(1,ndays+1):
            wk=date(year,month,d)-timedelta(days=date(year,month,d).weekday())
            for block in ("AM","PM"):
                if not all(bool(pattern[block.lower()][(pi,d)]) for pi in _priority_idx): continue
                rows=[sl for sl in normal if sl.day==d and sl.block==block and sl.department.startswith("CENTRO RO ")]
                if len(rows)>=len(_priority_idx): _priority_candidates_by_week.setdefault(wk,[]).append((d,block))

    cats=[c for c in ROTATION_CATEGORIES if c!="Onko RO"]
    cat_slot_counts={cat:sum(1 for sl in normal if rotation_category(sl)==cat) for cat in cats}
    # V2.5.107: post fairness is below mandatory cannot-work blocks. Tight
    # corridors are still tried first and widened only after HiGHS proves the
    # tighter one infeasible. This lets the engine preserve 0 hard-wish losses
    # instead of forcing a resident to work merely to keep a pretty post spread.
    trials=[(1,1),(1,2),(1,3),(1,4),(1,5),(1,6),(2,1),(2,2),(2,3),(2,4),(3,1),(3,2),(3,3),(3,4),(4,1),(4,2),(4,3),(4,4),(5,5),(6,6)]
    total_seconds=max(12.0,float(seconds)); per_trial=max(3.0,total_seconds/max(1,len(trials)))
    logs=[]
    best=None  # (dream_count, -critical_cap, -noncritical_cap, assignments, cc, nc, obj)
    dream_target=min(int(_PRIORITY_COLOCATION_MAX_PER_MONTH),len(_priority_candidates_by_week))

    for critical_cap,noncritical_cap in trials:
        mb=_V2564FastMB(); x={}
        for sl in normal:
            for pi in range(n):
                works=pattern["am"][(pi,sl.day)] if sl.block=="AM" else pattern["pm"][(pi,sl.day)]
                if not works: continue
                cost=(((pi+1)*37+(sl.idx+1)*13)%101)*1e-7
                if pattern["am"][(pi,sl.day)] and pattern["pm"][(pi,sl.day)]:
                    cost += (-0.02 if rotation_category(sl) in ("SPS RO","SPS UG") else 0.002)
                x[(pi,sl.idx)]=mb.var(cost=cost)

        # Slot coverage and fixed resident work blocks.
        for sl in normal:
            co={v:1.0 for (pi,sid),v in x.items() if sid==sl.idx}
            if not co:
                logs.append({"critical_cap":critical_cap,"noncritical_cap":noncritical_cap,"status":2,"reason":"unfillable slot"})
                break
            mb.constraint(co,1.0,1.0)
        else:
            for pi in range(n):
                for d in range(1,ndays+1):
                    for block in ("AM","PM"):
                        need=1.0 if (pattern["am"][(pi,d)] if block=="AM" else pattern["pm"][(pi,d)]) else 0.0
                        co={v:1.0 for (ppi,sid),v in x.items() if ppi==pi and byid[sid].day==d and byid[sid].block==block}
                        mb.constraint(co,need,need)

            expr={(pi,cat):{v:1.0 for (ppi,sid),v in x.items() if ppi==pi and rotation_category(byid[sid])==cat}
                  for pi in range(n) for cat in cats}

            # Structural post corridors.
            for cat in cats:
                total=int(cat_slot_counts.get(cat,0));
                if total<=0: continue
                cap=critical_cap if cat in CRITICAL_ROTATION_CATEGORIES else noncritical_cap
                adjusted=(baseline_weekend_volunteer_mode and cat=="SPS RO")
                offsets={pi:(int(volunteer_weekend_sps_const.get(pi,0)) if adjusted else 0) for pi in range(n)}
                fair_total=total-sum(offsets.values()) if adjusted else total
                if fair_total<0: fair_total=0
                if int(cap)<=1:
                    lo=fair_total//max(1,n); hi=int(math.ceil(float(fair_total)/float(max(1,n))))
                    for pi in range(n):
                        mb.constraint(expr[(pi,cat)],float(lo+offsets[pi]),float(hi+offsets[pi]))
                else:
                    # Pairwise fair-count corridor: |(raw_i-off_i)-(raw_j-off_j)| <= cap.
                    for i in range(n):
                        for j in range(i+1,n):
                            co=dict(expr[(i,cat)])
                            for v,c in expr[(j,cat)].items(): co[v]=co.get(v,0.0)-c
                            shift=float(offsets[i]-offsets[j])
                            mb.constraint(co,-float(cap)+shift,float(cap)+shift)

            # High-priority co-location: maximize feasible distinct weeks across the month.
            coloc_week_vars=[]
            for wk,cands in sorted(_priority_candidates_by_week.items()):
                cvars=[]
                for d,block in sorted(cands,key=lambda z:(z[0],0 if z[1]=="AM" else 1)):
                    cv=mb.var(0.0,1.0,True,cost=0.0); cvars.append(cv)
                    for pi in _priority_idx:
                        cvs={v:1.0 for (ppi,sid),v in x.items() if ppi==pi and byid[sid].day==d and byid[sid].block==block and byid[sid].department.startswith("CENTRO RO ")}
                        if not cvs:
                            mb.constraint({cv:1.0},0.0,0.0)
                        else:
                            co={cv:1.0}
                            for v in cvs: co[v]=co.get(v,0.0)-1.0
                            mb.constraint(co,-np.inf,0.0)
                if cvars:
                    wv=mb.var(0.0,1.0,True,cost=-10000.0); coloc_week_vars.append(wv)
                    for cv in cvars: mb.constraint({cv:1.0,wv:-1.0},-np.inf,0.0)
                    co={wv:1.0}
                    for cv in cvars: co[cv]=co.get(cv,0.0)-1.0
                    mb.constraint(co,-np.inf,0.0)
                    mb.constraint({cv:1.0 for cv in cvars},-np.inf,1.0)
            if coloc_week_vars:
                mb.constraint({wv:1.0 for wv in coloc_week_vars},-np.inf,float(_PRIORITY_COLOCATION_MAX_PER_MONTH))

            # Onko-zero -> Mammography first exposure, after structural corridor.
            mammo_seen=[]; mam_total=int(cat_slot_counts.get("Mamografijos",0) or 0)
            if mam_total>0:
                for pi in _onko_zero_indices:
                    me=expr.get((pi,"Mamografijos"),{})
                    if not me: continue
                    sv=mb.var(0.0,1.0,True,cost=-50.0); mammo_seen.append(sv)
                    co=dict(me); co[sv]=co.get(sv,0.0)-1.0
                    mb.constraint(co,0.0,np.inf)
                    co=dict(me); co[sv]=co.get(sv,0.0)-float(mam_total)
                    mb.constraint(co,-np.inf,0.0)

            res=mb.solve(per_trial,mip_gap=0.0)
            status=int(getattr(res,"status",99)); has=bool(res.x is not None)
            dream_count=(int(round(sum(float(res.x[v]) for v in coloc_week_vars))) if has and coloc_week_vars else 0)
            logs.append({"critical_cap":critical_cap,"noncritical_cap":noncritical_cap,"status":status,"incumbent":has,"solver":"V25105_RESILIENT_POST","dream_team_weeks":dream_count,"dream_team_target":dream_target})
            if has:
                assignments={}
                onko_by_day={sl.day:sl for sl in slots if sl.department=="Onko RO centre" and not sl.blocked and sl.idx not in fixed_gaps}
                for pi,p in enumerate(people):
                    for d in range(1,ndays+1):
                        if pattern["full"][(pi,d)]:
                            os=onko_by_day.get(d)
                            if os is None: return None,None,None,logs,None
                            assignments[os.idx]=p.initials
                for (pi,sid),v in x.items():
                    if float(res.x[v])>0.5: assignments[sid]=people[pi].initials
                candidate=(dream_count,-int(critical_cap),-int(noncritical_cap),assignments,critical_cap,noncritical_cap,float(getattr(res,"fun",0.0) or 0.0))
                if best is None or candidate[:3]>best[:3]:
                    best=candidate
                # Dream Team is above ordinary noncritical-post cosmetic spread.
                # Once every phase-1 feasible represented week is achieved, stop.
                if dream_count>=dream_target:
                    return assignments,critical_cap,noncritical_cap,logs,float(getattr(res,"fun",0.0) or 0.0)
                # Continue to wider post corridors to try to buy missing Dream-Team weeks.
                continue
            # A time-limit/no-incumbent does not prove infeasibility. If we already
            # have a valid tighter candidate, keep searching only when budget allows;
            # otherwise fail closed to the caller's clean-process retry.
            if status!=2 and best is None:
                return None,None,None,logs,None
            continue
        # broke because a slot had no eligible worker in this fixed pattern
        if best is None:
            return None,None,None,logs,None
    if best is not None:
        return best[3],best[4],best[5],logs,best[6]
    return None,None,None,logs,None

def _v2564_two_phase_fair_schedule(year, month, people, slots, targets, request_snapshot, time_limit=90.0):
    """Primary fairness-first generator with bounded automatic retries.

    V2.5.105 fixes a production failure mode where the fast two-phase model could
    time out without an incumbent on a slower Streamlit worker and immediately fall
    into the much larger legacy rescue MILP. The legacy model could then report an
    alarming ``ABSOLUTE HARD / COVERAGE FEASIBILITY FAILED`` even though the same
    request set is feasible in the intended two-phase architecture.

    A timeout/no-incumbent is never treated as proof of infeasibility. Each fast
    phase therefore gets one focused retry with a larger budget before the caller
    considers any legacy rescue path. This changes solver reliability only; it does
    not relax HARD, exact workload, Onko parity, weekend preference semantics, or
    post water-fill rules.
    """
    retry_trace=[]
    _fixed_legacy,gap_meta,gap_errors=plan_distributed_gaps(year,month,people,slots,targets)
    if gap_errors: return None

    gap_first=min(12.0,max(8.0,time_limit*0.07))
    fixed_gaps=_v2564_choose_fixed_gaps(year,month,slots,gap_meta,seconds=gap_first)
    if fixed_gaps is None:
        gap_retry=min(20.0,max(12.0,time_limit*0.10))
        retry_trace.append({"phase":"fixed_gaps","first_seconds":round(gap_first,1),"retry_seconds":round(gap_retry,1)})
        fixed_gaps=_v2564_choose_fixed_gaps(year,month,slots,gap_meta,seconds=gap_retry)
    if fixed_gaps is None: return None

    # V2.5.106: 22 s was a knife-edge on the real September model. Give the
    # single-pass work-pattern solve enough room to find its first incumbent so
    # we avoid the slower fail-then-retry path on ordinary cloud workers.
    work_first=min(35.0,max(30.0,time_limit*0.20))
    pattern=_v2564_work_pattern(year,month,people,slots,targets,fixed_gaps,seconds=work_first,structural_relaxation=False,weekend_spread_cap=1)
    if pattern is None:
        # V2.5.112 ADMIN RAW WEEKEND WATER-FILL: find the tightest feasible raw
        # weekend/Saturday/Sunday spread. Weekend wishes are not allowed to widen
        # this frontier. Lower tiers (Friday/double shaping/ordinary SOFT) may bend.
        pattern=None
        for _cap in (1,2,3,4):
            _sec=min(26.0,max(14.0,time_limit*0.14))
            retry_trace.append({"phase":"work_pattern_admin_weekend_waterfill","cap":_cap,"seconds":round(_sec,1)})
            pattern=_v2564_work_pattern(year,month,people,slots,targets,fixed_gaps,seconds=_sec,structural_relaxation=True,weekend_spread_cap=_cap)
            if pattern is not None:
                break
    if pattern is None: return None

    post_first=min(45.0,max(15.0,time_limit*0.35))
    assigned,critical_cap,noncritical_cap,post_log,post_obj=_v25105_assign_posts_resilient(year,month,people,slots,pattern,fixed_gaps,seconds=post_first)
    if assigned is None:
        # A phase-1 incumbent can satisfy every date/block preference yet be awkward
        # to label with the full post water-fill matrix. Re-solving the same post
        # model longer does not fix that structural coupling. Instead generate one
        # diversified, shorter phase-1 incumbent (same HARD + preference semantics)
        # and immediately test its post feasibility. This recovered the real
        # September request set that triggered the production error while keeping
        # VL's requested Sundays and all HARD constraints intact.
        rescue_work=min(35.0,max(30.0,time_limit*0.20))
        retry_trace.append({"phase":"post_feasibility_pattern_rescue","seconds":round(rescue_work,1)})
        rescue_pattern=_v2564_work_pattern(year,month,people,slots,targets,fixed_gaps,seconds=rescue_work,structural_relaxation=bool(pattern.get("structural_relaxation_mode",False)),weekend_spread_cap=int(pattern.get("weekend_spread_cap",1) or 1))
        if rescue_pattern is not None:
            rescue_post=min(40.0,max(20.0,time_limit*0.20))
            assigned2,cc2,nc2,post_log2,post_obj2=_v25105_assign_posts_resilient(
                year,month,people,slots,rescue_pattern,fixed_gaps,seconds=rescue_post
            )
            post_log=list(post_log or [])+[{"pattern_rescue":True,"seconds":round(rescue_post,1)}]+list(post_log2 or [])
            if assigned2 is not None:
                pattern=rescue_pattern
                assigned,critical_cap,noncritical_cap,post_obj=assigned2,cc2,nc2,post_obj2
    if assigned is None:
        post_retry=min(60.0,max(30.0,time_limit*0.30))
        retry_trace.append({"phase":"post_assignment_final_retry","seconds":round(post_retry,1)})
        assigned,critical_cap,noncritical_cap,post_log2,post_obj=_v25105_assign_posts_resilient(year,month,people,slots,pattern,fixed_gaps,seconds=post_retry)
        post_log=list(post_log or [])+[{"final_retry":True,"seconds":round(post_retry,1)}]+list(post_log2 or [])
    if assigned is None: return None
    stats=validate_schedule(year,month,people,slots,assigned,targets)
    g=stats.setdefault("global",{})
    # V2.5.112 Dream Team audit: count weeks with SP+GE+ŠR together on the same
    # CENTRO RO AM or PM block in the final SYSTEM assignment.
    _dream_weeks=[]
    _dream_group=set(_PRIORITY_COLOCATION_GROUP)
    _by_week={}
    for sl in slots:
        if sl.blocked or sl.department=="Onko RO centre" or not sl.department.startswith("CENTRO RO "):
            continue
        who=assigned.get(sl.idx)
        if who not in _dream_group:
            continue
        wk=date(year,month,sl.day)-timedelta(days=date(year,month,sl.day).weekday())
        _by_week.setdefault((wk,sl.day,sl.block),set()).add(who)
    for (wk,d,block),who in sorted(_by_week.items()):
        if who==_dream_group:
            _dream_weeks.append({"week_start":wk.isoformat(),"day":int(d),"block":block})
    g["dream_team_centro_weeks"]=len({x["week_start"] for x in _dream_weeks})
    g["dream_team_centro_details"]=_dream_weeks
    g["dream_team_centro_target_weeks"]=len({(date(year,month,d)-timedelta(days=date(year,month,d).weekday())).isoformat() for d in range(1,calendar.monthrange(year,month)[1]+1) if date(year,month,d).weekday()<5})
    g["admin_weekend_spread_cap_used"]=int(pattern.get("weekend_spread_cap",1) or 1)
    if int(g.get("hard_errors",9999) or 0)>0: return None
    rotation_spreads=g.get("rotation_monthly_spreads") or {}
    critical_spreads=dict(g.get("critical_structural_spreads") or {
        "SPS RO":int(rotation_spreads.get("SPS RO",999)),
        "SPS UG":int(rotation_spreads.get("SPS UG",999)),
        "SATURDAYS":int(g.get("saturday_monthly_spread",999) or 0),
        "SUNDAYS":int(g.get("sunday_monthly_spread",999) or 0),
        "FRIDAYS":int(g.get("friday_structural_spread_raw",999) or 0),
    })
    noncritical={cat:int(rotation_spreads.get(cat,0) or 0) for cat in NONCRITICAL_ROTATION_CATEGORIES}
    # Onko is solved in phase 1 under its separate even-pair parity constitution.
    worst_noncritical=max(list(noncritical.values())+[0])
    # V2.5.107: mandatory hard wishes outrank date-burden fairness. Post-label
    # corridors remain certified by phase 2, while Friday/weekend spreads are
    # allowed to exceed 1 only when the zero-hard structural fallback was needed.
    _post_critical=max(int(critical_spreads.get("SPS RO",0)),int(critical_spreads.get("SPS UG",0)))
    _date_critical=max(int(critical_spreads.get("SATURDAYS",0)),int(critical_spreads.get("SUNDAYS",0)),int(critical_spreads.get("FRIDAYS",0)))
    _relaxed=bool(pattern.get("structural_relaxation_mode",False))
    quality=bool(_post_critical<=int(critical_cap) and worst_noncritical<=int(noncritical_cap) and (_relaxed or _date_critical<=int(critical_cap)))
    if not quality: return None
    g.update({
        "solve_stage":"V2577_FRIDAY_ALL_POST_WATERFILL_TWO_PHASE",
        "solver_strategy":"TWO_PHASE_FRIDAY_AND_ALL_POST_STRUCTURAL_WATERFILL",
        "critical_structural_spreads":critical_spreads,
        "critical_worst_spread":max(critical_spreads.values()),
        "critical_01_status":"FOUND_TWO_PHASE_0_1" if int(critical_cap)<=1 else "STRUCTURAL_RELAXATION_USED_TWO_PHASE",
        "critical_spread_quality_gate_passed":bool(max(critical_spreads.values())<=1),
        "structural_fairness_relaxed_for_zero_hard":bool(pattern.get("structural_relaxation_mode",False)),
        "structural_fairness_relaxation_reason":("STRICT_0_1_WORK_PATTERN_DID_NOT_RETURN_A_CANDIDATE_IN_ITS_BOUNDED_PASS; NO_INFEASIBILITY_INFERRED; ZERO_RESIDENT_HARD_PRESERVED" if pattern.get("structural_relaxation_mode",False) else "NONE"),
        "noncritical_post_spreads":noncritical,
        "noncritical_worst_spread":worst_noncritical,
        "noncritical_guardrail_ceiling":int(noncritical_cap),
        "noncritical_guardrail_status":("STRUCTURAL_WATERFILL_0_1_TWO_PHASE" if int(noncritical_cap)<=1 else "PROVEN_EXCEPTION_0_2_TWO_PHASE" if int(noncritical_cap)==2 else "PROVEN_LAST_RESORT_0_3_TWO_PHASE"),
        "post_waterfill_structural_hard":True,
        "post_waterfill_target_spread":1,
        "post_waterfill_proven_ceiling":int(noncritical_cap),
        "post_waterfill_categories":list(NONCRITICAL_ROTATION_CATEGORIES),
        "post_waterfill_exchange_scope":"ALL_FIXED_AM_PM_POST_LABELS_JOINTLY; TWO_WAY_AND_MULTIWAY_CYCLES_IMPLICIT",
        "generation_quality_gate_passed":True,
        "generation_quality_issues":[],
        "v25105_fast_retry_trace":list(retry_trace),
        "v25106_single_pass_work_pattern":True,
        "v25107_resident_hard_zero_loss_required":True,
        "v25107_zero_hard_fallback_wish_mode":str(pattern.get("zero_hard_fallback_wish_mode","WEIGHTED_STRICT")),
        "v25105_fast_retry_used":bool(retry_trace),
        "resident_hard_min_total_found":int(pattern.get("resident_hard_min_total",0)),
        "resident_hard_minimum_proven":bool(pattern.get("resident_hard_minimum_proven",False)),
        "resident_hard_verified_min_total_cap":0,
        "resident_hard_current_max_lock":int(pattern.get("resident_hard_max_loss",0)),
        "post_assignment_search_log":post_log,
        "fixed_gap_slot_ids":sorted(int(x) for x in fixed_gaps),
        "count_date_separation":"Phase 1 enforces exact workload, Onko parity and Friday floor/ceil raw spread <=1 while choosing dates/blocks. Phase 2 jointly water-fills all non-Onko post labels with target raw spread <=1; wider post corridor is allowed only after the tighter post corridor is mathematically proven infeasible. ACTUAL voluntary swaps may later unbalance Friday/post exposure.",
        "sparse_first_exposure_required":True,
        "onko_first_exposure_required":False,
        "exact_workload_targets_required":True,
        "onko_even_pairs_required":True,
        "onko_monthly_spread_ceiling":2,
        "onko_consecutive_days_forbidden":True,
        "neutral_total_doubles_lock":int(pattern.get("neutral_total_doubles_lock",0) or 0),
        "double_neutral_baseline_spread_ceiling":int(DOUBLE_SPREAD_MAX),
        "double_monthly_spread_ceiling":None,
        "double_workstyle_override_allowed":True,
        "double_pattern_counts":pattern.get("double_counts",{}),
        "double_pattern_spread":int(pattern.get("double_spread",0) or 0),
        "workstyle_input_source":"FROZEN_SYSTEM_REQUEST_SNAPSHOT",
        "prefer12_people":pattern.get("prefer12_people",[]),
        "prefer12_cohort_size":int(pattern.get("prefer12_cohort_size",0) or 0),
        "prefer12_cohort_min":pattern.get("prefer12_cohort_min"),
        "prefer12_cohort_max":pattern.get("prefer12_cohort_max"),
        "workstyle_style_solve_proven":bool(pattern.get("workstyle_style_solve_proven",False)),
        "workstyle_priority_policy":"V25106_SINGLE_PASS_NEUTRAL_DOUBLE_COST_PLUS_SMALL_WORKSTYLE_TIEBREAK",
        "friday_structural_waterfill_required":True,
        "friday_structural_spread_ceiling":1,
        "friday_pattern_counts":pattern.get("friday_counts",{}),
        "friday_pattern_spread":int(pattern.get("friday_spread",0) or 0),
        "friday_pattern_floor":int(pattern.get("friday_floor",0) or 0),
        "friday_pattern_ceil":int(pattern.get("friday_ceil",0) or 0),
        "friday_post_coupling":"Phase 1 water-fills Friday work blocks; Phase 2 then jointly water-fills all non-Onko post labels on those fixed blocks.",
        "double_priority":"V2.5.106 single-pass objective keeps every AM+PM double positively costly and applies 6h/mixed/12h only as a smaller tie-breaker; work-style therefore redistributes preference pressure without creating a second blocking full-model solve. SPS RO / SPS UG are preferred when assigning labels to an already-needed AM+PM double. Onko RO is a separate 9h FULL day, not a double.",
        "baseline_weekend_volunteer_mode":False,
        "baseline_weekend_volunteers":list(pattern.get("baseline_weekend_volunteers") or []),
        "baseline_weekend_volunteer_locks":dict(pattern.get("baseline_weekend_volunteer_locks") or {}),
        "weekend_volunteer_counts":dict(pattern.get("weekend_volunteer_counts") or {}),
        "weekend_raw_counts":dict(pattern.get("weekend_raw_counts") or {}),
        "weekend_fair_counts":dict(pattern.get("weekend_fair_counts") or {}),
        "weekend_volunteer_policy":"V2.5.112 ADMIN rule: SYSTEM uses RAW weekend/Saturday/Sunday water-fill. Weekend work/off wishes and the weekend-style slider are audit-only and cannot buy extra SYSTEM weekend exposure. The engine searches the tightest feasible raw cap before lower fairness/SOFT tiers. ACTUAL swaps may later change real exposure after SP approval.",
    })
    msg=(
        "OK — exact-workload fairness-first two-phase schedule. Mėnesio krūvio targetas kiekvienam rezidentui išlaikytas tiksliai; Onko skiriamas poromis ir ne dvi kalendorines dienas iš eilės; "
        f"ADMIN RAW savaitgalių koridorius užrakintas ties mažiausiu rastu įmanomu cap={int(pattern.get('weekend_spread_cap',1) or 1)}; "
        f"SPS ir kitų postų paskirstymas optimizuotas pagal aukštesnius 0-HARD / Dream-Team / water-fill prioritetus. Tikslūs kiekvienos kategorijos spread rodomi statistikoje."
    )
    obj=float(pattern.get("objective_value",0.0) or 0.0)+float(post_obj or 0.0)
    return SolveResult(True,msg,assigned,targets,stats,obj,request_snapshot=request_snapshot)


def solve_schedule(year: int, month: int, people: List[Person], time_limit: float = 45.0) -> SolveResult:
    # V2.5.96 MONTHLY BASELINE FAIRNESS CONSTITUTION.
    # Every month starts from a clean fairness baseline. Historical ACTUAL/SYSTEM
    # exposure is retained for audit only and MUST NOT create compensatory catch-up
    # assignments in a later month. Only true cross-month safety/spacing state is
    # preserved (e.g. prior consecutive-weekend tail and prior-last-day Onko).
    people=[replace(
        p,
        prior_weekend_count=0,
        prior_holiday_count=0,
        prior_friday_count=0,
        prior_double_count=0,
        prior_weekday_day_count=0,
        prior_rotation_counts={},
        prior_resident_hard_loss_count=0,
    ) for p in people]
    # Freeze the exact request model before solving. Later ACTUAL schedules after
    # swaps are always scored against this original snapshot.
    request_snapshot=serialize_people_request_snapshot(people)
    # V2.5.64 primary architecture works directly from the resident-entered request
    # model. Legacy normalization remains available only for the legacy rescue path.
    fast_slots=make_slots(year,month)
    fast_targets=calculate_targets(year,month,people)
    fast_result=_v2564_two_phase_fair_schedule(
        year,month,people,fast_slots,fast_targets,request_snapshot,time_limit=max(90.0,float(time_limit))
    )
    if fast_result is not None and fast_result.ok:
        # V2.5.73 fail-closed invariant: even if a future solver/refactor path
        # accidentally bypasses one model row, no schedule can leave solve_schedule
        # as valid unless exact workload and even Onko pairing are explicitly proven
        # by the validator.
        fg=(fast_result.stats or {}).get("global",{})
        v2573_ok=(
            bool(fg.get("exact_workload_targets_passed",False))
            and bool(fg.get("onko_even_pairs_passed",False))
            and int(fg.get("onko_actual_filled_count",-1))==int(fg.get("onko_expected_filled_count",-2))
            and int(fg.get("resident_hard_total_losses",9999) or 0)==0
        )
        if v2573_ok:
            fg["v2573_onko_absolute_invariant_passed"]=True
            return fast_result
        return SolveResult(
            False,
            "V2.5.107 HARD-WISH / ONKO / TARGET INVARIANT FAILED — schedule intentionally rejected.",
            assignments=dict(fast_result.assignments),
            targets=dict(fast_result.targets),
            stats=fast_result.stats,
            objective_value=fast_result.objective_value,
            request_snapshot=request_snapshot,
        )

    # V2.5.105: preference-aware weekend semantics are implemented and validated
    # in the two-phase architecture. If that model still returns no incumbent after
    # its automatic retries, do NOT reinterpret a timeout as an ABSOLUTE-HARD
    # contradiction by dropping into the older all-in-one rescue model. Preserve any
    # existing draft at the UI layer and report a retryable solver failure instead.
    _has_weekend_positive_request=any(
        any(date(year,month,int(d)).weekday()>=5 for d in (set(p.preferred)|set(p.preferred_am)|set(p.preferred_pm)))
        for p in people
    )
    if _has_weekend_positive_request:
        return SolveResult(
            False,
            "PREFERENCE-AWARE GENERATION DID NOT FINISH AFTER AUTOMATIC RETRIES. "
            "The request set was not proven infeasible and no HARD rule is being blamed. "
            "Existing draft, if any, remains unchanged; run generation again if needed.",
            targets=fast_targets,
            request_snapshot=request_snapshot,
        )

    # V2.5.27 PRE-SOLVE PREFERENCE NORMALIZATION (legacy rescue path).
    people, preference_normalization = normalize_preferences_against_engine(people,year,month)

    slots = make_slots(year, month)
    targets = calculate_targets(year,month,people)
    fixed_gap_ids,gap_plan,gap_plan_errors=plan_distributed_gaps(year,month,people,slots,targets)
    optional_gap_days=set(gap_plan.get("optional_gap_days",[]))
    optional_gap_counts={int(d):int(c) for d,c in (gap_plan.get("optional_gap_counts") or {}).items()}
    if not optional_gap_counts:
        optional_gap_counts={int(d):1 for d in optional_gap_days}
    if gap_plan_errors:
        return SolveResult(
            False,
            "GAP PLAN HARD ERROR — " + "; ".join(gap_plan_errors),
            targets=targets,
        )

    mb = ModelBuilder()

    # V2.5.29: track individual SOFT objective contributions separately so
    # the engine can first optimize global fairness, then lock fairness guardrails,
    # then optimize true individual SOFT inside that fair solution space.
    preference_cost_delta: Dict[int, float] = {}

    # V2.5.50 TWO-DIMENSIONAL PREFERENCE FAIRNESS.
    # Vertical axis (strict rank): RESIDENT HARD -> SOFT-1 -> SOFT-2 -> SOFT-3.
    # Horizontal axis (inside each rank): resident request counts are equalized
    # before a resident with extra requests can consume lower layers. This is
    # progressive-filling / water-filling entitlement fairness. N/A residents
    # are absent from that row and remain flexible capacity.
    soft_tier_expr: Dict[str, Dict[int, dict]] = {
        tier:{pi:{"count":0,"const":0.0,"coeffs":{}} for pi in range(len(people))}
        for tier in ("SOFT1","SOFT2","SOFT3")
    }

    def add_soft_tier_term(tier: str, pi: int, coeffs: Optional[Dict[int,float]] = None, const: float = 0.0):
        rec=soft_tier_expr[tier][pi]
        rec["count"] += 1
        rec["const"] += float(const)
        for vidx,coef in (coeffs or {}).items():
            rec["coeffs"][vidx]=rec["coeffs"].get(vidx,0.0)+float(coef)

    def add_preference_cost(var_idx: int, delta: float):
        mb.c[var_idx] += float(delta)
        preference_cost_delta[var_idx] = preference_cost_delta.get(var_idx, 0.0) + float(delta)

    x: Dict[Tuple[int, int], int] = {}

    # Assignment variables.
    for pi, p in enumerate(people):
        for s in slots:
            allowed = (
                (not s.blocked)
                and (s.idx not in fixed_gap_ids)
                and (not normal_assignment_blocked(p, s.day, s.block))
            )

            # Very small tie-breaker. CENTRO RO is slightly rewarded to avoid
            # large holes there when optional coverage must be sacrificed.
            cost = 0.000001 * (pi + 1) + 0.00000001 * s.idx
            if s.department.startswith("CENTRO RO"):
                cost -= 0.10

            x[(pi, s.idx)] = mb.var(
                f"x[{p.initials},{s.day},{s.department},{s.block}]",
                cost=cost,
                lb=0,
                ub=1 if allowed else 0,
                integer=True,
            )

    # Slot coverage — V2.5.40 distributed gap-DAY layout.
    # Non-gap days are fully covered (except explicit blocked closures).
    # Each planned optional-gap day has EXACTLY one empty optional slot, but the
    # solver chooses which row/station is best to leave empty.
    optional_slots=[
        s for s in slots
        if not s.blocked and not s.mandatory and s.department!="Onko RO centre"
    ]

    for s in slots:
        co={x[(pi,s.idx)]:1 for pi in range(len(people))}
        if s.blocked or s.idx in fixed_gap_ids:
            mb.constraint(co,0,0,f"blocked/fixed-gap {s.idx}")
        elif s.department=="Onko RO centre":
            mb.constraint(co,1,1,f"Onko filled {s.idx}")
        elif s.mandatory:
            mb.constraint(co,1,1,f"mandatory {s.idx}")
        elif s.day not in optional_gap_days:
            mb.constraint(co,1,1,f"optional fully covered {s.idx}")
        else:
            mb.constraint(co,0,1,f"gap-day optional {s.idx}")

    # Exactly the planned number of optional rows is empty on each gap day.
    # Vacation-adjusted targets may require more than one gap on a weekday.
    for d in sorted(optional_gap_days):
        day_opts=[s for s in optional_slots if s.day==d]
        need=int(optional_gap_counts.get(d,1))
        if len(day_opts)<need:
            return SolveResult(False,f"GAP PLAN HARD ERROR — day {d} needs {need} optional gaps but has only {len(day_opts)} optional slots",targets=targets)
        co={}
        for s in day_opts:
            for pi in range(len(people)):
                co[x[(pi,s.idx)]]=1
        filled=len(day_opts)-need
        mb.constraint(co,filled,filled,f"exactly {need} gaps day {d}")

    # Balance WHICH workplaces absorb the unavoidable gaps.
    # gap_count(cat) = candidate gap-day slots in cat - filled slots in cat.
    gap_count_by_cat={}
    for cat in ROTATION_CATEGORIES:
        cat_opts=[s for s in optional_slots if s.day in optional_gap_days and rotation_category(s)==cat]
        if not cat_opts:
            continue
        gc=mb.var(f"gap_count[{cat}]",cost=0,lb=0,ub=len(cat_opts),integer=False)
        co={gc:1}
        for s in cat_opts:
            for pi in range(len(people)):
                co[x[(pi,s.idx)]]=co.get(x[(pi,s.idx)],0)+1
        mb.constraint(co,len(cat_opts),len(cat_opts),f"gap count identity {cat}")
        gap_count_by_cat[cat]=gc

    if gap_count_by_cat:
        gmax=mb.var("gap_category_max",cost=160.0,lb=0,ub=len(optional_gap_days),integer=False)
        gmin=mb.var("gap_category_min",cost=-40.0,lb=0,ub=len(optional_gap_days),integer=False)
        for cat,gc in gap_count_by_cat.items():
            mb.constraint({gc:1,gmax:-1},-np.inf,0,f"gap category max {cat}")
            mb.constraint({gc:1,gmin:-1},0,np.inf,f"gap category min {cat}")
        # REAL guardrail: unavoidable gaps may not all pile into one service.
        mb.constraint({gmax:1,gmin:-1},-np.inf,2,"gap category spread <= 2")

    # Spread repeated CENTRO/ADC row sacrifice as a lower-order tie-breaker.
    family_groups={}
    for s in optional_slots:
        if s.day not in optional_gap_days:
            continue
        family_groups.setdefault((s.department,s.block),[]).append(s)
    for fam,fs in family_groups.items():
        # Tiny reward for keeping every family covered; repeated gaps become less attractive.
        if not fs:
            continue
        filled=mb.var(f"gap_family_filled[{fam[0]},{fam[1]}]",cost=-2.0,lb=0,ub=len(fs),integer=False)
        co={filled:-1}
        for s in fs:
            for pi in range(len(people)):
                co[x[(pi,s.idx)]]=co.get(x[(pi,s.idx)],0)+1
        mb.constraint(co,0,0,f"gap family filled identity {fam}")

    # Explicit Onko parity consistency.
    onko_slots=[s for s in slots if s.department=="Onko RO centre" and not s.blocked]
    onko_fill=len(onko_slots) if len(onko_slots)%2==0 else len(onko_slots)-1
    mb.constraint(
        {x[(pi,s.idx)]:1 for pi in range(len(people)) for s in onko_slots},
        onko_fill,onko_fill,"Onko monthly coverage"
    )

    # Symmetry breaking for identical CENTRO RO rows:
    # if fewer than 4 are filled, lower-numbered rows are filled first.
    for d in range(1, calendar.monthrange(year, month)[1] + 1):
        if date(year, month, d).weekday() >= 5:
            continue
        for block in ("AM", "PM"):
            centro = [
                s for s in slots
                if s.day == d and s.block == block and s.department.startswith("CENTRO RO ")
            ]
            centro = sorted(centro, key=lambda s: int(s.department.split()[-1]))
            for left, right in zip(centro, centro[1:]):
                co = {}
                for pi in range(len(people)):
                    co[x[(pi, left.idx)]] = co.get(x[(pi, left.idx)], 0) + 1
                    co[x[(pi, right.idx)]] = co.get(x[(pi, right.idx)], 0) - 1
                mb.constraint(co, 0, np.inf, f"Centro occupancy order {d} {block} {left.idx}")

    priority_colocation_week_vars=[]
    _priority_idx=[]
    _ini_to_pi={p.initials:pi for pi,p in enumerate(people)}
    if all(ini in _ini_to_pi for ini in _PRIORITY_COLOCATION_GROUP):
        _priority_idx=[_ini_to_pi[ini] for ini in _PRIORITY_COLOCATION_GROUP]
        _by_week={}
        for d in range(1, calendar.monthrange(year,month)[1]+1):
            dt=date(year,month,d); wk=dt-timedelta(days=dt.weekday())
            for block in ("AM","PM"):
                centro=[sl for sl in slots if sl.day==d and sl.block==block and not sl.blocked and sl.idx not in fixed_gap_ids and sl.department.startswith("CENTRO RO ")]
                if len(centro)<len(_priority_idx):
                    continue
                cv=mb.var(f"priority_coloc[{d},{block}]",cost=0.0,lb=0,ub=1,integer=True)
                for pi in _priority_idx:
                    co={cv:1.0}
                    for sl in centro:
                        co[x[(pi,sl.idx)]]=co.get(x[(pi,sl.idx)],0.0)-1.0
                    mb.constraint(co,-np.inf,0.0,f"priority coloc eligibility {people[pi].initials} {d} {block}")
                _by_week.setdefault(wk,[]).append(cv)
        for wk,cvars in sorted(_by_week.items()):
            wv=mb.var(f"priority_coloc_week[{wk.isoformat()}]",cost=0.0,lb=0,ub=1,integer=True)
            priority_colocation_week_vars.append(wv)
            co={wv:-1.0}
            for cv in cvars:
                co[cv]=co.get(cv,0.0)+1.0
                mb.constraint({cv:1.0,wv:-1.0},-np.inf,0.0,f"priority coloc block implies week {wk} {cv}")
            mb.constraint(co,0.0,np.inf,f"priority coloc week hit {wk}")
            mb.constraint({cv:1.0 for cv in cvars},-np.inf,1.0,f"priority coloc max one block week {wk}")
        if priority_colocation_week_vars:
            mb.constraint({wv:1.0 for wv in priority_colocation_week_vars},-np.inf,float(_PRIORITY_COLOCATION_MAX_PER_MONTH),"priority coloc monthly cap")

    # Exact workload targets (x2 so 1.5 Onko remains integer).
    for pi, p in enumerate(people):
        mb.constraint(
            {x[(pi, s.idx)]: s.workload2 for s in slots},
            targets[p.initials] * 2,
            targets[p.initials] * 2,
            f"target {p.initials}"
        )

    _, ndays = calendar.monthrange(year, month)
    by_day = {d: [s for s in slots if s.day == d] for d in range(1, ndays + 1)}

    workday: Dict[Tuple[int, int], int] = {}
    doubles: Dict[Tuple[int, int], int] = {}
    # V2.5.71: identifies avoidable doubles made entirely from ordinary posts.
    # A double containing SPS RO or SPS UG is considered clinically useful;
    # Sunday duties are already SPS RO. Onko RO is FULL 9h and never an AM+PM double.
    noncritical_double_vars: List[int] = []

    # Day realism + preference variables.
    for pi, p in enumerate(people):
        for d in range(1, ndays + 1):
            ds = by_day[d]
            if not ds:
                continue

            wd = date(year, month, d).weekday()
            is_weekday = wd < 5

            # Weekday-preference applies to DISTINCT weekdays worked.
            y = mb.var(f"workday[{p.initials},{d}]", cost=0.0, integer=False)
            workday[(pi, d)] = y
            add_preference_cost(
                y,
                ((-0.22 * p.weekday_preference) if is_weekday else 0.0)
                - 0.14 * p.spread_preference
            )

            # V2.5.13 ACTIVE-PREFERENCE POLICY:
            # An explicitly entered date preference is a real SOFT objective;
            # N/A means zero preference objective and therefore remains flexible.
            # Exact active wishes are meaningful individual SOFT objectives.
            # N/A is zero-weight flexible capacity. Global fatigue/fairness rules
            # remain shared engine logic and are not duplicated as 16 preferences.
            ACTIVE_DATE_REWARD = float(rule_value("active_date_reward"))
            if d in p.preferred:
                add_preference_cost(y, -ACTIVE_DATE_REWARD)
                add_soft_tier_term("SOFT2",pi,{y:1.0})

            # Explicit "Noriu laisvos" is treated symmetrically as an active
            # exact-date SOFT preference, not as equivalent to N/A.
            if d in p.soft_free:
                add_preference_cost(y, ACTIVE_DATE_REWARD)
                add_soft_tier_term("SOFT1",pi,{y:-1.0},const=1.0)

            # Morning / afternoon SOFT preferences act on matching assignment blocks.
            # FULL overlaps both halves. A resident may therefore express precise
            # wishes such as "morning off, prefer afternoon work" on the same date.
            am_match_vars=[]
            pm_match_vars=[]
            for s in ds:
                xv = x[(pi, s.idx)]
                if blocks_overlap(s.block, "AM"):
                    am_match_vars.append(xv)
                if blocks_overlap(s.block, "PM"):
                    pm_match_vars.append(xv)
                if d in p.preferred_am and blocks_overlap(s.block, "AM"):
                    add_preference_cost(xv, -ACTIVE_DATE_REWARD)
                if d in p.preferred_pm and blocks_overlap(s.block, "PM"):
                    add_preference_cost(xv, -ACTIVE_DATE_REWARD)
                if d in p.soft_free_am and blocks_overlap(s.block, "AM"):
                    add_preference_cost(xv, ACTIVE_DATE_REWARD)
                if d in p.soft_free_pm and blocks_overlap(s.block, "PM"):
                    add_preference_cost(xv, ACTIVE_DATE_REWARD)

            # AM/FULL and PM/FULL overlap constraints below guarantee each sum is
            # in [0,1], so these are exact linear 0..1 satisfaction expressions.
            if d in p.preferred_am:
                add_soft_tier_term("SOFT2",pi,{v:1.0 for v in am_match_vars})
            if d in p.preferred_pm:
                add_soft_tier_term("SOFT2",pi,{v:1.0 for v in pm_match_vars})
            if d in p.soft_free_am:
                add_soft_tier_term("SOFT1",pi,{v:-1.0 for v in am_match_vars},const=1.0)
            if d in p.soft_free_pm:
                add_soft_tier_term("SOFT1",pi,{v:-1.0 for v in pm_match_vars},const=1.0)

            # Spread preference may shape WHEN already-needed doubles occur, but
            # V2.5.71 shift-length preference must never manufacture extra doubles.
            # The group-level double total is frozen before personal work-style SOFT.
            dd = mb.var(f"double[{p.initials},{d}]", cost=0.0, integer=False)
            doubles[(pi, d)] = dd
            add_preference_cost(dd, 0.34 * p.spread_preference)

            sum_day = {x[(pi, s.idx)]: 1 for s in ds}

            # Exact continuous workday indicator:
            # y <= sum(x) and y >= every x. Since x is binary, y is forced to 0/1
            # without being an additional integer variable.
            c2 = dict(sum_day); c2[y] = -1
            mb.constraint(c2, 0, np.inf, f"workday <= assignments {p.initials} {d}")
            for s in ds:
                mb.constraint(
                    {y:1,x[(pi,s.idx)]:-1},
                    0,np.inf,
                    f"workday >= slot {p.initials} {d} {s.idx}"
                )

            # max 2 assignments/day.
            mb.constraint(sum_day, 0, int(rule_value("max_assignments_per_day")), f"max assignments/day {p.initials} {d}")

            # dd = 1 iff sum_day == 2; continuous auxiliary is sufficient.
            c3 = dict(sum_day); c3[dd] = -1
            mb.constraint(c3, -np.inf, 1, f"double lower {p.initials} {d}")  # sum_day - dd <= 1
            c4 = dict(sum_day); c4[dd] = -2
            mb.constraint(c4, 0, np.inf, f"double upper {p.initials} {d}")  # sum_day - 2dd >= 0

            # V2.5.71 double-quality preference: if a double is necessary, prefer
            # using it on clinically important exposure (SPS RO / SPS UG; Sunday
            # duties are SPS RO). Ordinary-post-only doubles remain feasible only
            # when higher-ranked constraints leave no better placement.
            critical_ds=[ss for ss in ds if rotation_category(ss) in ("SPS RO","SPS UG")]
            ndv=mb.var(f"V2571_noncritical_double[{p.initials},{d}]",cost=0.0,lb=0.0,ub=1.0,integer=False)
            q={ndv:1.0,dd:-1.0}
            for ss in critical_ds:
                q[x[(pi,ss.idx)]]=q.get(x[(pi,ss.idx)],0.0)+1.0
            mb.constraint(q,0.0,np.inf,f"V2571 noncritical double detector {p.initials} {d}")
            noncritical_double_vars.append(ndv)

            # Fatigue-aware doubles.
            # A double after 3 consecutive worked days receives a strong SOFT penalty.
            # This keeps the MILP fast while steering doubles toward fresher people/days.
            if d >= 4:
                y1 = workday[(pi, d - 1)]
                y2 = workday[(pi, d - 2)]
                y3 = workday[(pi, d - 3)]
                z_after3 = mb.var(
                    f"double_after_3_consecutive_days[{p.initials},{d}]",
                    cost=90.0,
                    integer=False
                )
                # z >= dd_today + y1 + y2 + y3 - 3
                mb.constraint(
                    {z_after3: 1, dd: -1, y1: -1, y2: -1, y3: -1},
                    -3, np.inf,
                    f"fatigue after3 {p.initials} {d}"
                )

            # AM/FULL overlap and PM/FULL overlap.
            am = [s for s in ds if s.block in ("AM", "FULL")]
            pm = [s for s in ds if s.block in ("PM", "FULL")]
            mb.constraint({x[(pi, s.idx)]: 1 for s in am}, 0, 1, f"AM overlap {p.initials} {d}")
            mb.constraint({x[(pi, s.idx)]: 1 for s in pm}, 0, 1, f"PM overlap {p.initials} {d}")

    # ------------------------------------------------------------------
    # V2.5.107 RESIDENT-HARD AUDIT LEDGER.
    # `Negaliu dirbti` is mandatory in SYSTEM generation. Assignment variables are
    # already fixed to zero on those blocks. Loss variables are retained solely to
    # prove/report that the generated draft has exactly 0 RESIDENT-HARD misses.
    # ------------------------------------------------------------------
    resident_hard_loss_vars: Dict[Tuple[int,str,int,str],int] = {}
    resident_hard_loss_count: Dict[int,int] = {}
    resident_hard_request_count: Dict[int,int] = {}
    resident_hard_honored_count: Dict[int,int] = {}
    cumulative_resident_hard_loss: Dict[int,int] = {}
    total_resident_hard_requests=0

    for pi,p in enumerate(people):
        reqs=[]
        # Whole-day request subsumes half-day entries on the same date so a single
        # human request cannot be double-counted by malformed/imported data.
        full_days=set(p.unavailable)
        am_days=set(p.unavailable_am)-full_days
        pm_days=set(p.unavailable_pm)-full_days
        reqs += [("resident_hard",d,"FULL") for d in sorted(full_days)]
        reqs += [("resident_hard",d,"AM") for d in sorted(am_days)]
        reqs += [("resident_hard",d,"PM") for d in sorted(pm_days)]
        total_resident_hard_requests += len(reqs)
        resident_hard_request_count[pi]=len(reqs)
        losses=[]
        for kind,d,block in reqs:
            lv=mb.var(
                f"resident_hard_loss[{p.initials},{d},{block}]",
                cost=0.0,lb=0.0,ub=1.0,integer=False
            )
            resident_hard_loss_vars[(pi,kind,d,block)]=lv
            losses.append(lv)
            if block=="FULL":
                y=workday[(pi,d)]
                mb.constraint({lv:1.0,y:-1.0},0.0,0.0,
                              f"resident hard whole-day loss {p.initials} {d}")
            else:
                ovs=[
                    x[(pi,s.idx)] for s in by_day[d]
                    if blocks_overlap(s.block,block)
                ]
                co={lv:1.0}
                for xv in ovs:
                    co[xv]=co.get(xv,0.0)-1.0
                # AM/FULL and PM/FULL overlap caps guarantee sum(ovs)<=1.
                mb.constraint(co,0.0,0.0,
                              f"resident hard {block} loss {p.initials} {d}")

        cnt=mb.var(
            f"resident_hard_loss_count[{p.initials}]",
            cost=0.0,lb=0.0,ub=max(0,len(reqs)),integer=False
        )
        resident_hard_loss_count[pi]=cnt
        co={cnt:-1.0}
        for lv in losses:
            co[lv]=co.get(lv,0.0)+1.0
        mb.constraint(co,0.0,0.0,f"resident hard loss count {p.initials}")

        honored=mb.var(
            f"resident_hard_honored_count[{p.initials}]",cost=0.0,
            lb=0.0,ub=max(0,len(reqs)),integer=False
        )
        resident_hard_honored_count[pi]=honored
        mb.constraint({honored:1.0,cnt:1.0},float(len(reqs)),float(len(reqs)),
                      f"resident hard honored identity {p.initials}")

        prior=max(0,int(getattr(p,"prior_resident_hard_loss_count",0) or 0))
        cum=mb.var(
            f"cumulative_resident_hard_loss[{p.initials}]",
            cost=0.0,lb=0.0,ub=prior+max(0,len(reqs))+50,integer=False
        )
        cumulative_resident_hard_loss[pi]=cum
        mb.constraint({cum:1.0,cnt:-1.0},prior,prior,
                      f"cumulative resident hard loss {p.initials}")

    resident_hard_total_loss=mb.var(
        "resident_hard_total_loss",cost=0.0,lb=0.0,
        ub=max(0,total_resident_hard_requests),integer=False
    )
    co={resident_hard_total_loss:-1.0}
    for v in resident_hard_loss_count.values():
        co[v]=co.get(v,0.0)+1.0
    mb.constraint(co,0.0,0.0,"resident hard total loss identity")
    # V2.5.107 fail-closed constitutional lock: no SYSTEM draft may contain a
    # resident-entered `Negaliu dirbti` violation.
    mb.constraint({resident_hard_total_loss:1.0},0.0,0.0,"V25107 resident hard zero-loss mandatory")

    rh_current_max=mb.var(
        "resident_hard_current_max_loss",cost=0.0,lb=0.0,
        ub=max(0,total_resident_hard_requests),integer=False
    )
    rh_current_min=mb.var(
        "resident_hard_current_min_loss",cost=0.0,lb=0.0,
        ub=max(0,total_resident_hard_requests),integer=False
    )
    max_prior_rh=max([int(getattr(p,"prior_resident_hard_loss_count",0) or 0) for p in people]+[0])
    rh_cumulative_max=mb.var(
        "resident_hard_cumulative_max_loss",cost=0.0,lb=0.0,
        ub=max_prior_rh+max(0,total_resident_hard_requests)+50,integer=False
    )
    rh_cumulative_min=mb.var(
        "resident_hard_cumulative_min_loss",cost=0.0,lb=0.0,
        ub=max_prior_rh+max(0,total_resident_hard_requests)+50,integer=False
    )
    for pi,p in enumerate(people):
        cnt=resident_hard_loss_count[pi]
        cum=cumulative_resident_hard_loss[pi]
        mb.constraint({cnt:1.0,rh_current_max:-1.0},-np.inf,0.0,
                      f"resident hard current max {p.initials}")
        mb.constraint({cnt:1.0,rh_current_min:-1.0},0.0,np.inf,
                      f"resident hard current min {p.initials}")
        mb.constraint({cum:1.0,rh_cumulative_max:-1.0},-np.inf,0.0,
                      f"resident hard cumulative max {p.initials}")
        mb.constraint({cum:1.0,rh_cumulative_min:-1.0},0.0,np.inf,
                      f"resident hard cumulative min {p.initials}")

    # V2.5.50 HORIZONTAL WATER-FILLING FOR RESIDENT HARD.
    # If request counts are 2,2,2,4, the common 2,2,2,2 layer is protected
    # before the fourth resident's extra two requests are considered.
    active_rh_people=[pi for pi,n in resident_hard_request_count.items() if int(n)>0]
    rh_min_honored=None; rh_max_honored=None
    if active_rh_people:
        max_rh_req=max(resident_hard_request_count[pi] for pi in active_rh_people)
        rh_min_honored=mb.var("resident_hard_waterfill_min_honored",cost=0.0,lb=0.0,ub=max_rh_req,integer=False)
        rh_max_honored=mb.var("resident_hard_waterfill_max_honored",cost=0.0,lb=0.0,ub=max_rh_req,integer=False)
        for pi in active_rh_people:
            hv=resident_hard_honored_count[pi]
            mb.constraint({hv:1.0,rh_min_honored:-1.0},0.0,np.inf,
                          f"resident hard waterfill min {people[pi].initials}")
            mb.constraint({hv:1.0,rh_max_honored:-1.0},-np.inf,0.0,
                          f"resident hard waterfill max {people[pi].initials}")

    # HARD Lithuanian labour-law / rest-safety layer — V2.5.2.
    # Current scheduler hours: AM 08-14 (6h), PM 14-20 (6h), FULL 08-17 (9h).
    # AM+PM on the same day is legal within this model: exactly 12h.
    def _known_hours(s):
        return 9.0 if s.block == "FULL" else 6.0

    # Maximum 12h of known scheduled work per workday.
    for pi, p in enumerate(people):
        for d in range(1, ndays + 1):
            ds = by_day[d]
            mb.constraint(
                {x[(pi, s.idx)]: _known_hours(s) for s in ds},
                0, float(rule_value("max_hours_per_day")),
                f"max hours/day {p.initials} {d}"
            )

    # V2.5.53 ABSOLUTE FATIGUE FLOOR. Every rolling 7-day window must
    # contain at least one completely free day (<=6 worked days). The active
    # Rule Profile may be stricter, but cannot weaken this constitutional cap.
    effective_max_workdays7=min(
        int(rule_value("max_workdays_rolling7")),
        int(FATIGUE_MAX_WORKDAYS_ROLLING7),
    )
    for pi, p in enumerate(people):
        for start_d in range(1, ndays - 6 + 1):
            mb.constraint(
                {workday[(pi, d)]: 1 for d in range(start_d, start_d + 7)},
                0, effective_max_workdays7,
                f"V2553 free-day rolling7 {p.initials} {start_d}"
            )

    # V2.5.53: 60h in one week is no longer an acceptable generated pattern.
    # Keep <=48 known scheduled hours in every rolling 7 days as an ABSOLUTE
    # fatigue guardrail, while the staged optimizer below actively aims around
    # 40h and water-fills weekly burden across residents. A Rule Profile value
    # below 48 tightens the cap; a value above 48 cannot weaken it.
    effective_max_hours7=min(
        float(rule_value("max_hours_rolling7")),
        float(FATIGUE_ROLLING7_HARD_CEILING_HOURS),
    )
    rolling7_hours: Dict[Tuple[int,int],int] = {}
    rolling7_over40: Dict[Tuple[int,int],int] = {}
    max_rolling7_over40=mb.var(
        "V2553_max_rolling7_over40",cost=0.0,lb=0.0,
        ub=max(0.0,effective_max_hours7-WEEKLY_LOAD_SOFT_TARGET_HOURS),integer=False
    )
    total_rolling7_over40=mb.var(
        "V2553_total_rolling7_over40",cost=0.0,lb=0.0,
        ub=max(1.0,float(len(people)*max(1,ndays-6))*effective_max_hours7),integer=False
    )
    total_over_expr={total_rolling7_over40:-1.0}
    for pi, p in enumerate(people):
        for start_d in range(1, ndays - 6 + 1):
            win = [s for s in slots if start_d <= s.day <= start_d + 6]
            hv=mb.var(
                f"rolling7_hours[{p.initials},{start_d}]",cost=0.0,lb=0.0,
                ub=effective_max_hours7,integer=False
            )
            rolling7_hours[(pi,start_d)]=hv
            co={x[(pi,s.idx)]:_known_hours(s) for s in win}; co[hv]=-1.0
            mb.constraint(co,0.0,0.0,f"V2553 rolling7 hours identity {p.initials} {start_d}")
            mb.constraint({hv:1.0},0.0,effective_max_hours7,f"V2553 rolling7 48h cap {p.initials} {start_d}")
            ov=mb.var(
                f"rolling7_over40[{p.initials},{start_d}]",cost=0.0,lb=0.0,
                ub=max(0.0,effective_max_hours7-WEEKLY_LOAD_SOFT_TARGET_HOURS),integer=False
            )
            rolling7_over40[(pi,start_d)]=ov
            # ov >= hours - 40
            mb.constraint(
                {hv:1.0,ov:-1.0},-np.inf,float(WEEKLY_LOAD_SOFT_TARGET_HOURS),
                f"V2553 rolling7 over40 {p.initials} {start_d}"
            )
            mb.constraint({ov:1.0,max_rolling7_over40:-1.0},-np.inf,0.0,f"V2553 max over40 {p.initials} {start_d}")
            total_over_expr[ov]=total_over_expr.get(ov,0.0)+1.0
    mb.constraint(total_over_expr,0.0,0.0,"V2553 total rolling7 over40 identity")

    # Calendar-week load matrix (resident x week). This is the horizontal
    # water-filling view of temporal workload: within each Mon-Sun week, avoid
    # one resident carrying a large hour block while peers are light. Partial
    # first/last weeks are compared only across residents in the same week.
    week_keys=[]
    week_days={}
    for d in range(1,ndays+1):
        dt=date(year,month,d)
        key=(dt.isocalendar().year,dt.isocalendar().week)
        if key not in week_days:
            week_keys.append(key); week_days[key]=[]
        week_days[key].append(d)
    calendar_week_hours: Dict[Tuple[int,int],int] = {}
    calendar_week_spread_pairs: Dict[int,Tuple[int,int]] = {}
    worst_calendar_week_spread=mb.var(
        "V2553_worst_calendar_week_hours_spread",cost=0.0,lb=0.0,
        ub=effective_max_hours7,integer=False
    )
    for wi,key in enumerate(week_keys):
        days=set(week_days[key])
        week_slot_list=[s for s in slots if s.day in days]
        zmax=mb.var(f"V2553_week{wi}_hours_max",cost=0.0,lb=0.0,ub=effective_max_hours7,integer=False)
        zmin=mb.var(f"V2553_week{wi}_hours_min",cost=0.0,lb=0.0,ub=effective_max_hours7,integer=False)
        calendar_week_spread_pairs[wi]=(zmax,zmin)
        mb.constraint({zmax:1.0,zmin:-1.0,worst_calendar_week_spread:-1.0},-np.inf,0.0,f"V2553 worst calendar week spread {wi}")
        for pi,p in enumerate(people):
            hv=mb.var(f"calendar_week_hours[{p.initials},{wi}]",cost=0.0,lb=0.0,ub=effective_max_hours7,integer=False)
            calendar_week_hours[(pi,wi)]=hv
            co={x[(pi,s.idx)]:_known_hours(s) for s in week_slot_list}; co[hv]=-1.0
            mb.constraint(co,0.0,0.0,f"V2553 calendar week hours identity {p.initials} {wi}")
            mb.constraint({hv:1.0,zmax:-1.0},-np.inf,0.0,f"V2553 calendar week max {p.initials} {wi}")
            mb.constraint({hv:1.0,zmin:-1.0},0.0,np.inf,f"V2553 calendar week min {p.initials} {wi}")

    # Double-shift recovery protocol. A single 12h double makes another double
    # on the following day undesirable. Two consecutive doubles are a stronger
    # structural event: the next day is restricted to PM-only or completely off
    # (no AM/FULL), which also makes three consecutive doubles impossible. If a
    # PM shift is still used after two doubles, the optimizer separately prefers
    # a fully free recovery day whenever feasible.
    consecutive_double_pair_vars=[]
    post_two_double_work_vars=[]
    for pi,p in enumerate(people):
        for d in range(2,ndays+1):
            pv=mb.var(f"V2553_consecutive_double_pair[{p.initials},{d-1}-{d}]",cost=0.0,lb=0.0,ub=1.0,integer=False)
            mb.constraint({pv:1.0,doubles[(pi,d-1)]:-1.0,doubles[(pi,d)]:-1.0},-1.0,np.inf,f"V2553 consecutive double pair {p.initials} {d}")
            consecutive_double_pair_vars.append(pv)
        for d in range(3,ndays+1):
            d1=doubles[(pi,d-2)]; d2=doubles[(pi,d-1)]
            # If both previous days were doubles, today cannot contain AM/FULL.
            for s in by_day[d]:
                if blocks_overlap(s.block,"AM"):
                    mb.constraint(
                        {d1:1.0,d2:1.0,x[(pi,s.idx)]:1.0},-np.inf,2.0,
                        f"V2553 after two doubles PM-or-off {p.initials} {d} {s.idx}"
                    )
            rv=mb.var(f"V2553_work_after_two_doubles[{p.initials},{d}]",cost=0.0,lb=0.0,ub=1.0,integer=False)
            mb.constraint({rv:1.0,d1:-1.0,d2:-1.0,workday[(pi,d)]:-1.0},-2.0,np.inf,f"V2553 prefer off after two doubles {p.initials} {d}")
            post_two_double_work_vars.append(rv)

    # >=11h uninterrupted rest between separate workdays.
    # With current standard shifts all ordinary adjacent-day combinations
    # already leave >=12h, but pairwise logic is kept as a hard guardrail.
    start_hour = {"AM": 8, "FULL": 8, "PM": 14}
    end_hour = {"AM": 14, "FULL": 17, "PM": 20}
    for pi, p in enumerate(people):
        for d in range(1, ndays):
            today_slots = [s for s in slots if s.day == d]
            next_slots = [s for s in slots if s.day == d + 1]
            for a in today_slots:
                for b in next_slots:
                    rest = (24 - end_hour[a.block]) + start_hour[b.block]
                    if rest < float(rule_value("min_rest_hours")):
                        mb.constraint(
                            {x[(pi, a.idx)]: 1, x[(pi, b.idx)]: 1},
                            0, 1,
                            f"DK min11h rest {p.initials} {d} {a.idx}-{b.idx}"
                        )

    # HARD backup availability — V2.5.32 LOCKED.
    # Every filled WEEKEND, SPS RO and SPS UG shift must have at least one
    # HARD-available resident with no overlapping normal assignment.
    # Self-claimed backup reservations are already blocked from overlapping
    # normal work through Person.reserved_backup / normal_assignment_blocked().
    for covered_slot in [s for s in slots if backup_required_slot(s)]:
        candidates = [
            (pi,p) for pi,p in enumerate(people)
            if not absolute_unavailable_for_block(p, covered_slot.day, covered_slot.block)
        ]
        if not candidates:
            continue
        busy={}
        for pi,_p in candidates:
            for s in slots:
                if s.day != covered_slot.day:
                    continue
                if not blocks_overlap(s.block, covered_slot.block):
                    continue
                busy[x[(pi,s.idx)]]=1
        # All current backup-required shifts are mandatory. Therefore one
        # candidate must remain free for the covered block.
        mb.constraint(
            busy, 0, len(candidates)-1,
            f"backup availability {covered_slot.department} {covered_slot.block} day {covered_slot.day}"
        )

    # Optional administrative rule: even Onko assignment count.
    if bool(rule_value("onko_even_required")):
        for pi, p in enumerate(people):
            pairs = mb.var(
                f"onko_pairs[{p.initials}]",
                cost=0, lb=0, ub=max(1, len(onko_slots) // 2 + 1), integer=True
            )
            co = {x[(pi, s.idx)]: 1 for s in onko_slots}
            co[pairs] = -2
            mb.constraint(co, 0, 0, f"Onko even {p.initials}")

    # V2.5.68 ABSOLUTE Onko recovery guard, mirrored in the legacy rescue path.
    onko_by_day={d:[s for s in onko_slots if s.day==d] for d in range(1,ndays+1)}
    for pi,p in enumerate(people):
        if bool(getattr(p,"prior_last_day_onko",False)) and onko_by_day.get(1):
            mb.constraint(
                {x[(pi,s.idx)]:1 for s in onko_by_day[1]},
                0,0,f"Onko previous-month recovery {p.initials}"
            )
        for d in range(1,ndays):
            co={}
            for s in onko_by_day.get(d,[])+onko_by_day.get(d+1,[]):
                co[x[(pi,s.idx)]]=1
            if co:
                mb.constraint(co,0,1,f"Onko no consecutive days {p.initials} {d}-{d+1}")

    # Weekend hard structure from active Rule Profile.
    if bool(rule_value("weekend_unique_required")):
        saturdays = [d for d in range(1, ndays + 1) if date(year, month, d).weekday() == 5]
        weekend_cap = int(rule_value("weekend_max_assignments_per_resident"))
        for sat in saturdays:
            sun = sat + 1
            if sun <= ndays and date(year, month, sun).weekday() == 6:
                ws = [s for s in slots if s.day in (sat, sun)]
                for pi, p in enumerate(people):
                    mb.constraint(
                        {x[(pi, s.idx)]: 1 for s in ws},
                        0, weekend_cap,
                        f"weekend resident cap {p.initials} {sat}"
                    )

    # Consecutive-day fatigue.
    # Spread/cluster preference is already modeled through distinct workdays and doubles.
    # Here we only penalize very long 5+ day runs using continuous auxiliaries
    # to keep the solver fast enough for a web app.
    for pi, p in enumerate(people):
        for run_len, penalty in [(5, 55.0), (6, 130.0), (7, 300.0)]:
            for start in range(1, ndays - run_len + 2):
                ys = [workday[(pi, d)] for d in range(start, start + run_len)]
                z = mb.var(
                    f"run{run_len}[{p.initials},{start}]",
                    cost=penalty,
                    integer=False
                )
                co = {v: 1 for v in ys}
                co[z] = -1
                mb.constraint(co, -np.inf, run_len - 1,
                              f"run penalty {p.initials} {start} {run_len}")

    # -----------------------
    # FAIRNESS LAYER
    # -----------------------
    weekend_slots = [s for s in slots if s.weekday >= 5]

    # V2.5.90 BASELINE WEEKEND VOLUNTEER OVERRIDE.
    # Explicit "Pageidauju dirbti" on a weekend is treated as volunteering for an
    # unpopular duty. In the first month with no published weekend history, these
    # voluntary assignments may sit OUTSIDE the current fairness count. The
    # remaining non-voluntary weekend/SPS-RO burden is still water-filled.
    #
    # Raw exposure is still written to publication history. Therefore later months
    # remember the extra voluntary load and cumulative fairness resumes normally.
    weekend_volunteer_slots_by_pi={
        pi:[s for s in weekend_slots if preferred_for_slot(p,s.day,s.block)]
        for pi,p in enumerate(people)
    }
    # V2.5.104: explicit weekend “Pageidauju dirbti” is voluntary burden in every
    # month, not only in a first-history month. Remaining non-voluntary burden is
    # still water-filled; prior-month history remains audit-only.
    baseline_weekend_volunteer_mode=any(bool(v) for v in weekend_volunteer_slots_by_pi.values())

    # Mirror the primary two-phase solver: Saturday and Sunday fairness is applied
    # to non-voluntary burden. Raw weekend uniqueness still applies above.
    if baseline_weekend_volunteer_mode:
        for _wd,_label in ((5,"Saturday"),(6,"Sunday")):
            _dayslots=[sl for sl in weekend_slots if sl.weekday==_wd]
            for i in range(len(people)):
                for j in range(i+1,len(people)):
                    _co={}
                    for sl in _dayslots:
                        _ci=0.0 if preferred_for_slot(people[i],sl.day,sl.block) else 1.0
                        _cj=0.0 if preferred_for_slot(people[j],sl.day,sl.block) else 1.0
                        if _ci: _co[x[(i,sl.idx)]]=_co.get(x[(i,sl.idx)],0.0)+_ci
                        if _cj: _co[x[(j,sl.idx)]]=_co.get(x[(j,sl.idx)],0.0)-_cj
                    if _co:
                        mb.constraint(_co,-1.0,1.0,f"V25104 volunteer-adjusted {_label} fairness {people[i].initials}-{people[j].initials}")

    holiday_days = public_holiday_days_in_month(year,month)
    holiday_slots = [s for s in slots if s.day in holiday_days and not s.blocked]
    weekday_slots = [s for s in slots if s.weekday < 5 and s.day not in holiday_days]
    friday_slots = [s for s in slots if s.weekday == 4]
    # Weekend groups are Saturday+Sunday pairs; a month-opening Sunday uses
    # anchor 0 so cross-month clustering can still be discouraged.
    weekend_group_anchors=sorted(set(
        s.day if s.weekday==5 else s.day-1 for s in weekend_slots
    ))
    weekend_groups={a:[s for s in weekend_slots if (s.day if s.weekday==5 else s.day-1)==a] for a in weekend_group_anchors}

    weekend_count = {}
    voluntary_weekend_count = {}
    voluntary_weekend_request_cap = {}
    fairness_weekend_count = {}
    cumulative_fair_weekend = {}
    voluntary_weekend_sps_ro_count = {}
    fairness_sps_ro_count = {}
    cumulative_fair_sps_ro = {}
    holiday_count = {}
    cumulative_holiday = {}
    weekend_group_worked = {}
    critical_temporal_penalty_vars = []
    critical_temporal_penalty_weights = {}
    cumulative_weekend = {}
    weekday_assignment_count = {}
    weekday_day_count = {}
    cumulative_weekday_day = {}
    friday_count = {}
    cumulative_friday = {}
    double_count = {}
    cumulative_double = {}

    max_prior_weekend = max([p.prior_weekend_count for p in people] + [0])
    max_prior_holiday = max([p.prior_holiday_count for p in people] + [0])
    max_prior_friday = max([p.prior_friday_count for p in people] + [0])
    max_prior_double = max([p.prior_double_count for p in people] + [0])
    max_prior_weekday_day = max([p.prior_weekday_day_count for p in people] + [0])

    # V2.5.15 ROTATION / WORKPLACE DIVERSITY FAIRNESS.
    # Goal A: within each month, expose every resident to as many DIFFERENT
    # workplaces as feasible.
    # Goal B: if one resident gets less of a workplace this month, carry that
    # imbalance forward through prior_rotation_counts and preferentially catch
    # it up in later published SYSTEM schedules.
    # This is a CORE FAIRNESS objective, not a feasibility blocker: HARD safety,
    # availability and exact workload constraints still remain absolute.
    rotation_count = {}
    cumulative_rotation = {}
    rotation_used = {}
    rotation_slots = {
        cat:[s for s in slots if (not s.blocked) and rotation_category(s)==cat]
        for cat in ROTATION_CATEGORIES
    }
    for pi,p in enumerate(people):
        for cat in ROTATION_CATEGORIES:
            cat_slots=rotation_slots[cat]
            rc=mb.var(
                f"rotation_count[{p.initials},{cat}]",
                cost=0, lb=0, ub=max(1,len(cat_slots)), integer=False
            )
            rotation_count[(pi,cat)]=rc
            co={x[(pi,s.idx)]:1 for s in cat_slots}; co[rc]=-1
            mb.constraint(co,0,0,f"rotation count {p.initials} {cat}")

            # Binary "seen this workplace this month". A reward for this variable
            # maximizes breadth before allowing repeated placements where avoidable.
            used=mb.var(
                f"rotation_used[{p.initials},{cat}]",
                # Diversity matters as a tie-breaker after count equality.
                cost=-30.0, lb=0, ub=1, integer=False
            )
            rotation_used[(pi,cat)]=used
            # rc <= M*used and rc >= used.
            mb.constraint({rc:1,used:-max(1,len(cat_slots))},-np.inf,0,
                          f"rotation used upper {p.initials} {cat}")
            mb.constraint({rc:1,used:-1},0,np.inf,
                          f"rotation used lower {p.initials} {cat}")

            prior=int(p.prior_rotation_counts.get(cat,0))
            cum=mb.var(
                f"cumulative_rotation[{p.initials},{cat}]",
                cost=0,lb=0,ub=prior+len(cat_slots)+200,integer=False
            )
            cumulative_rotation[(pi,cat)]=cum
            mb.constraint({cum:1,rc:-1},prior,prior,
                          f"cumulative rotation {p.initials} {cat}")

    # V2.5.104 legacy-rescue parity with the primary two-phase solver: residents
    # receiving zero Onko RO get a strong tie-break priority for at least one
    # remaining Mammography exposure. The structural post corridor still dominates.
    onko_zero_mammo_bonus_vars=[]
    _onko_M=max(2,len(rotation_slots.get("Onko RO",[])))
    _mammo_M=max(1,len(rotation_slots.get("Mamografijos",[])))
    for pi,p in enumerate(people):
        _orc=rotation_count[(pi,"Onko RO")]
        _mrc=rotation_count[(pi,"Mamografijos")]
        _oz=mb.var(f"onko_zero[{p.initials}]",cost=0.0,lb=0,ub=1,integer=True)
        mb.constraint({_orc:1.0,_oz:float(_onko_M)},-np.inf,float(_onko_M),f"Onko zero upper {p.initials}")
        mb.constraint({_orc:1.0,_oz:2.0},2.0,np.inf,f"Onko zero lower {p.initials}")
        _bonus=mb.var(f"onko_zero_mammo_bonus[{p.initials}]",cost=0.0,lb=0,ub=1,integer=True)
        mb.constraint({_bonus:1.0,_oz:-1.0},-np.inf,0.0,f"Onko-zero mammo bonus eligibility {p.initials}")
        mb.constraint({_mrc:1.0,_bonus:-1.0},0.0,np.inf,f"Onko-zero mammo exposure {p.initials}")
        onko_zero_mammo_bonus_vars.append(_bonus)

    for pi, p in enumerate(people):
        # CRITICAL WEEKEND EXPOSURE. Count ALL weekend assignments, including
        # voluntarily preferred dates: educational exposure and fatigue still exist.
        # Persistent weekend work-style may choose the upper/lower fair layer, but
        # it cannot change or bypass this structural raw-count row.
        wc = mb.var(
            f"weekend_count[{p.initials}]",
            cost=0.0,
            lb=0, ub=max(1, len(weekend_slots)), integer=False
        )
        weekend_count[pi] = wc
        co = {x[(pi, s.idx)]: 1 for s in weekend_slots}; co[wc] = -1
        mb.constraint(co, 0, 0, f"critical weekend exposure count {p.initials}")

        # Persistent weekend work-style preference: one or two SOFT3 entitlement
        # units depending on slider strength. Structural weekend fairness is solved
        # and locked before SOFT3, so this can only decide who receives the upper
        # or lower layer when the equal split has a remainder.
        _we_pref=max(-2,min(2,int(getattr(p,"weekend_preference",0) or 0)))
        _weekend_norm=max(1.0,float(len(weekend_group_anchors)))
        for _ in range(abs(_we_pref)):
            if _we_pref>0:
                add_soft_tier_term("SOFT3",pi,{wc:1.0/_weekend_norm})
            elif _we_pref<0:
                add_soft_tier_term("SOFT3",pi,{wc:-1.0/_weekend_norm},const=1.0)

        cum = mb.var(
            f"cumulative_weekend[{p.initials}]",
            cost=0, lb=0, ub=max_prior_weekend + len(weekend_slots) + 20, integer=False
        )
        cumulative_weekend[pi] = cum
        mb.constraint(
            {cum: 1, wc: -1},
            p.prior_weekend_count, p.prior_weekend_count,
            f"cumulative critical weekend exposure {p.initials}"
        )

        volunteer_slots=weekend_volunteer_slots_by_pi.get(pi,[])
        volunteer_days=sorted({s.day for s in volunteer_slots})
        volunteer_hit_vars=[]
        for d in volunteer_days:
            ds=[s for s in weekend_slots if s.day==d]
            if d in p.preferred:
                # One whole-day request = one satisfaction unit if any weekend
                # assignment is worked on that date.
                hv=mb.var(f"voluntary_weekend_day_hit[{p.initials},{d}]",cost=0.0,lb=0,ub=1,integer=False)
                vals=[x[(pi,s.idx)] for s in ds]
                for xv in vals:
                    mb.constraint({xv:1.0,hv:-1.0},-np.inf,0.0,f"voluntary weekend day hit upper {p.initials} {d}")
                co={hv:1.0}
                for xv in vals:
                    co[xv]=co.get(xv,0.0)-1.0
                mb.constraint(co,-np.inf,0.0,f"voluntary weekend day hit lower {p.initials} {d}")
                volunteer_hit_vars.append(hv)
            else:
                if d in p.preferred_am:
                    amvals=[x[(pi,s.idx)] for s in ds if blocks_overlap(s.block,"AM")]
                    if amvals:
                        hv=mb.var(f"voluntary_weekend_am_hit[{p.initials},{d}]",cost=0.0,lb=0,ub=1,integer=False)
                        for xv in amvals: mb.constraint({xv:1.0,hv:-1.0},-np.inf,0.0,f"vol weekend am upper {p.initials} {d}")
                        co={hv:1.0}; [co.__setitem__(xv,co.get(xv,0.0)-1.0) for xv in amvals]
                        mb.constraint(co,-np.inf,0.0,f"vol weekend am lower {p.initials} {d}")
                        volunteer_hit_vars.append(hv)
                if d in p.preferred_pm:
                    pmvals=[x[(pi,s.idx)] for s in ds if blocks_overlap(s.block,"PM")]
                    if pmvals:
                        hv=mb.var(f"voluntary_weekend_pm_hit[{p.initials},{d}]",cost=0.0,lb=0,ub=1,integer=False)
                        for xv in pmvals: mb.constraint({xv:1.0,hv:-1.0},-np.inf,0.0,f"vol weekend pm upper {p.initials} {d}")
                        co={hv:1.0}; [co.__setitem__(xv,co.get(xv,0.0)-1.0) for xv in pmvals]
                        mb.constraint(co,-np.inf,0.0,f"vol weekend pm lower {p.initials} {d}")
                        volunteer_hit_vars.append(hv)

        voluntary_weekend_request_cap[pi]=int(len(volunteer_hit_vars))
        vwc=mb.var(
            f"voluntary_weekend_count[{p.initials}]",
            cost=0.0, lb=0, ub=max(1,len(volunteer_hit_vars)), integer=False
        )
        voluntary_weekend_count[pi]=vwc
        vco={hv:1.0 for hv in volunteer_hit_vars}
        vco[vwc]=-1.0
        mb.constraint(vco,0.0,0.0,f"voluntary weekend count {p.initials}")

        fwc=mb.var(
            f"fairness_weekend_count[{p.initials}]",
            cost=0.0, lb=0, ub=max(1,len(weekend_slots)), integer=False
        )
        fairness_weekend_count[pi]=fwc
        if baseline_weekend_volunteer_mode:
            mb.constraint(
                {fwc:1.0,wc:-1.0,vwc:1.0},0.0,0.0,
                f"baseline volunteer-adjusted weekend count {p.initials}"
            )
        else:
            mb.constraint(
                {fwc:1.0,wc:-1.0},0.0,0.0,
                f"standard weekend fairness count {p.initials}"
            )

        cfw=mb.var(
            f"cumulative_fair_weekend[{p.initials}]",
            cost=0.0, lb=0, ub=max_prior_weekend+len(weekend_slots)+20, integer=False
        )
        cumulative_fair_weekend[pi]=cfw
        mb.constraint(
            {cfw:1.0,fwc:-1.0},
            p.prior_weekend_count,p.prior_weekend_count,
            f"cumulative fairness weekend {p.initials}"
        )

        # Weekend duty is SPS RO in this roster. The same explicit voluntary
        # weekend assignment must therefore be removed from BOTH the weekend and
        # SPS-RO fairness counts during baseline mode, otherwise raw SPS-RO 0-1
        # would silently cancel the intended volunteer exception.
        vsps=mb.var(
            f"voluntary_weekend_sps_ro_count[{p.initials}]",
            cost=0.0, lb=0, ub=max(1,len(volunteer_hit_vars)), integer=False
        )
        voluntary_weekend_sps_ro_count[pi]=vsps
        # Weekend service is SPS RO in the current roster, so the voluntary SPS-RO
        # exemption equals the request-semantic weekend volunteer hit count.
        mb.constraint({vsps:1.0,vwc:-1.0},0.0,0.0,f"voluntary weekend SPS RO count {p.initials}")

        fsps=mb.var(
            f"fairness_sps_ro_count[{p.initials}]",
            cost=0.0, lb=0, ub=max(1,len(rotation_slots["SPS RO"])), integer=False
        )
        fairness_sps_ro_count[pi]=fsps
        raw_sps=rotation_count[(pi,"SPS RO")]
        if baseline_weekend_volunteer_mode:
            mb.constraint(
                {fsps:1.0,raw_sps:-1.0,vsps:1.0},0.0,0.0,
                f"baseline volunteer-adjusted SPS RO count {p.initials}"
            )
        else:
            mb.constraint(
                {fsps:1.0,raw_sps:-1.0},0.0,0.0,
                f"standard SPS RO fairness count {p.initials}"
            )

        cfsps=mb.var(
            f"cumulative_fair_sps_ro[{p.initials}]",
            cost=0.0,
            lb=0,
            ub=int(p.prior_rotation_counts.get("SPS RO",0))+len(rotation_slots["SPS RO"])+20,
            integer=False
        )
        cumulative_fair_sps_ro[pi]=cfsps
        mb.constraint(
            {cfsps:1.0,fsps:-1.0},
            int(p.prior_rotation_counts.get("SPS RO",0)),
            int(p.prior_rotation_counts.get("SPS RO",0)),
            f"cumulative fairness SPS RO {p.initials}"
        )

        # V2.5.58 holiday duty exposure. A holiday is a separate burden/choice axis
        # even when it falls on a weekend. One resident may cover at most one shift
        # on a given public holiday; cumulative SYSTEM history is used for rotation.
        hc=mb.var(f"holiday_count[{p.initials}]",cost=0.0,lb=0,ub=max(1,len(holiday_slots)),integer=False)
        holiday_count[pi]=hc
        hco={x[(pi,s.idx)]:1 for s in holiday_slots}; hco[hc]=-1
        mb.constraint(hco,0,0,f"holiday exposure count {p.initials}")
        hcum=mb.var(f"cumulative_holiday[{p.initials}]",cost=0.0,lb=0,ub=max_prior_holiday+len(holiday_slots)+20,integer=False)
        cumulative_holiday[pi]=hcum
        mb.constraint({hcum:1,hc:-1},p.prior_holiday_count,p.prior_holiday_count,f"cumulative holiday exposure {p.initials}")
        for hd in sorted(holiday_days):
            hs=[s for s in holiday_slots if s.day==hd]
            if hs:
                mb.constraint({x[(pi,s.idx)]:1 for s in hs},0,1,f"holiday one-shift cap {p.initials} {hd}")

        # Critical weekend temporal spacing. Equal monthly counts are not enough:
        # avoid concentrating them in consecutive weekends when an equivalent
        # count distribution exists. This is optimized AFTER Resident-HARD.
        for gi,a in enumerate(weekend_group_anchors):
            gs=weekend_groups[a]
            wv=mb.var(f"weekend_group_worked[{p.initials},{a}]",cost=0.0,lb=0,ub=1,integer=True)
            weekend_group_worked[(pi,gi)]=wv
            gco={x[(pi,ss.idx)]:1.0 for ss in gs}
            # any assignment => worked=1; worked=1 => at least one assignment
            for ss in gs:
                mb.constraint({x[(pi,ss.idx)]:1.0,wv:-1.0},-np.inf,0.0,f"weekend group upper {p.initials} {a} {ss.idx}")
            gco[wv]=-1.0
            mb.constraint(gco,0.0,np.inf,f"weekend group lower {p.initials} {a}")

        for gi in range(max(0,len(weekend_group_anchors)-1)):
            pv=mb.var(f"consecutive_weekend_pair[{p.initials},{gi}]",cost=0.0,lb=0,ub=1,integer=True)
            mb.constraint({pv:1.0,weekend_group_worked[(pi,gi)]:-1.0,weekend_group_worked[(pi,gi+1)]:-1.0},-1.0,np.inf,f"consecutive weekend pair {p.initials} {gi}")
            critical_temporal_penalty_vars.append(pv); critical_temporal_penalty_weights[pv]=20.0
        for gi in range(max(0,len(weekend_group_anchors)-2)):
            tv=mb.var(f"consecutive_weekend_triple[{p.initials},{gi}]",cost=0.0,lb=0,ub=1,integer=True)
            mb.constraint({tv:1.0,weekend_group_worked[(pi,gi)]:-1.0,weekend_group_worked[(pi,gi+1)]:-1.0,weekend_group_worked[(pi,gi+2)]:-1.0},-2.0,np.inf,f"consecutive weekend triple {p.initials} {gi}")
            critical_temporal_penalty_vars.append(tv); critical_temporal_penalty_weights[tv]=120.0
        if weekend_group_anchors:
            first=weekend_group_worked[(pi,0)]
            prior_streak=max(0,int(getattr(p,"prior_consecutive_weekend_streak",0) or 0))
            if prior_streak:
                # Crossing the month boundary is still consecutive exposure.
                critical_temporal_penalty_vars.append(first)
                critical_temporal_penalty_weights[first]=critical_temporal_penalty_weights.get(first,0.0)+(35.0 if prior_streak==1 else 180.0)

        # Weekday assignment count.
        wa = mb.var(
            f"weekday_assignments[{p.initials}]",
            cost=0, lb=0, ub=len(weekday_slots), integer=False
        )
        weekday_assignment_count[pi] = wa
        co = {x[(pi, s.idx)]: 1 for s in weekday_slots}; co[wa] = -1
        mb.constraint(co, 0, 0, f"weekday assignments {p.initials}")

        # Distinct weekdays worked.
        wdc = mb.var(
            f"weekday_days[{p.initials}]",
            cost=0, lb=0, ub=weekday_count(year, month), integer=False
        )
        weekday_day_count[pi] = wdc
        co = {workday[(pi, d)]: 1 for d in range(1, ndays + 1)
              if date(year, month, d).weekday() < 5}
        co[wdc] = -1
        mb.constraint(co, 0, 0, f"weekday days {p.initials}")

        _wd_pref=max(-2,min(2,int(getattr(p,"weekday_preference",0) or 0)))
        _weekday_norm=max(1.0,float(weekday_count(year,month)))
        for _ in range(abs(_wd_pref)):
            if _wd_pref>0:
                add_soft_tier_term("SOFT3",pi,{wdc:1.0/_weekday_norm})
            elif _wd_pref<0:
                add_soft_tier_term("SOFT3",pi,{wdc:-1.0/_weekday_norm},const=1.0)

        cwd = mb.var(
            f"cumulative_weekday_days[{p.initials}]",
            cost=0, lb=0,
            ub=max_prior_weekday_day + weekday_count(year, month) + 40,
            integer=False
        )
        cumulative_weekday_day[pi] = cwd
        mb.constraint(
            {cwd: 1, wdc: -1},
            p.prior_weekday_day_count, p.prior_weekday_day_count,
            f"cumulative weekday days {p.initials}"
        )

        # V2.5.77 structural Friday burden: ALL Friday assignments count.
        # A preferred Friday is still a real Friday exposure and therefore does
        # not disappear from the SYSTEM water-fill denominator.
        fc = mb.var(
            f"fridays[{p.initials}]",
            cost=0, lb=0, ub=len(friday_slots), integer=False
        )
        friday_count[pi] = fc
        co = {x[(pi, s.idx)]: 1 for s in friday_slots}; co[fc] = -1
        mb.constraint(co, 0, 0, f"V2577 structural Friday count {p.initials}")

        cfr = mb.var(
            f"cumulative_fridays[{p.initials}]",
            cost=0, lb=0,
            ub=max_prior_friday + len(friday_slots) + 40,
            integer=False
        )
        cumulative_friday[pi] = cfr
        mb.constraint(
            {cfr: 1, fc: -1},
            p.prior_friday_count, p.prior_friday_count,
            f"cumulative Friday {p.initials}"
        )

        # Double burden.
        dc = mb.var(
            f"doubles_total[{p.initials}]",
            cost=0, lb=0, ub=ndays, integer=False
        )
        double_count[pi] = dc
        co = {doubles[(pi, d)]: 1 for d in range(1, ndays + 1)}
        co[dc] = -1
        mb.constraint(co, 0, 0, f"double count {p.initials}")

        cdb = mb.var(
            f"cumulative_doubles[{p.initials}]",
            cost=0, lb=0,
            ub=max_prior_double + ndays + 40,
            integer=False
        )
        cumulative_double[pi] = cdb
        mb.constraint(
            {cdb: 1, dc: -1},
            p.prior_double_count, p.prior_double_count,
            f"cumulative double {p.initials}"
        )
        double_denom=max(1.0,float(ndays))
        shift_len=max(0,min(3,int(getattr(p,"shift_length_preference",0) or 0)))
        if shift_len==1 or (shift_len==0 and p.avoid_doubles):
            # V2.5.71: 6h/12h is one symmetric long-term work-style axis. It
            # redistributes the frozen group double pool; it does not outrank
            # concrete monthly time-off/work-date requests.
            add_soft_tier_term("SOFT3",pi,{dc:-1.0/double_denom},const=1.0)
        elif shift_len==3:
            add_soft_tier_term("SOFT3",pi,{dc:1.0/double_denom})
        elif shift_len==2:
            # Balance 12h double-days against ordinary 6h single-shift days;
            # 9h Onko FULL days are excluded from this personal 6h/12h preference.
            mix_abs=mb.var(f"shift_length_mixed_deviation[{p.initials}]",cost=0.0,lb=0.0,ub=ndays,integer=False)
            expr={dc:2.0}
            for d in range(1,ndays+1):
                expr[workday[(pi,d)]]=expr.get(workday[(pi,d)],0.0)-1.0
            for s in slots:
                if s.department=="Onko RO centre" and not s.blocked:
                    expr[x[(pi,s.idx)]]=expr.get(x[(pi,s.idx)],0.0)+1.0
            cpos={mix_abs:1.0}; cneg={mix_abs:1.0}
            for v,c in expr.items():
                cpos[v]=cpos.get(v,0.0)-c
                cneg[v]=cneg.get(v,0.0)+c
            mb.constraint(cpos,0.0,np.inf,f"mixed shift length + {p.initials}")
            mb.constraint(cneg,0.0,np.inf,f"mixed shift length - {p.initials}")
            add_soft_tier_term("SOFT3",pi,{mix_abs:-1.0/double_denom},const=1.0)
        if p.spread_preference:
            if p.spread_preference>0:
                add_soft_tier_term("SOFT3",pi,{dc:-1.0/double_denom},const=1.0)
            else:
                add_soft_tier_term("SOFT3",pi,{dc:1.0/double_denom})

    # SPS RO / SPS UG temporal spacing tie-breakers. The primary count spread
    # remains the hard structural guard; these variables only reduce avoidable
    # day-to-day clustering inside that fixed exposure frontier.
    for pi,p in enumerate(people):
        for cat in CRITICAL_ROTATION_CATEGORIES:
            day_used={}
            for d in range(1,ndays+1):
                ds=[ss for ss in rotation_slots[cat] if ss.day==d]
                if not ds:
                    continue
                uv=mb.var(f"critical_day_used[{p.initials},{cat},{d}]",cost=0.0,lb=0,ub=1,integer=True)
                day_used[d]=uv
                for ss in ds:
                    mb.constraint({x[(pi,ss.idx)]:1.0,uv:-1.0},-np.inf,0.0,f"critical day upper {p.initials} {cat} {d} {ss.idx}")
                co={x[(pi,ss.idx)]:1.0 for ss in ds}; co[uv]=-1.0
                mb.constraint(co,0.0,np.inf,f"critical day lower {p.initials} {cat} {d}")
            for d in range(1,ndays):
                if d not in day_used or d+1 not in day_used:
                    continue
                pv=mb.var(f"critical_consecutive_day[{p.initials},{cat},{d}]",cost=0.0,lb=0,ub=1,integer=True)
                mb.constraint({pv:1.0,day_used[d]:-1.0,day_used[d+1]:-1.0},-1.0,np.inf,f"critical consecutive day {p.initials} {cat} {d}")
                critical_temporal_penalty_vars.append(pv); critical_temporal_penalty_weights[pv]=critical_temporal_penalty_weights.get(pv,0.0)+6.0

    fairness_spread_vars: Dict[str, Tuple[int, int]] = {}

    def add_spread_minimizer(name, variables, weight, ub):
        zmax = mb.var(f"{name}_max", cost=weight, lb=0, ub=ub, integer=False)
        zmin = mb.var(f"{name}_min", cost=-weight, lb=0, ub=ub, integer=False)
        fairness_spread_vars[name] = (zmax, zmin)
        for pi in variables:
            mb.constraint({variables[pi]: 1, zmax: -1}, -np.inf, 0, f"{name} max {pi}")
            mb.constraint({variables[pi]: 1, zmin: -1}, 0, np.inf, f"{name} min {pi}")
        return zmax, zmin

    # V2.5.48 TARGET-NORMALIZED POST SPREAD.
    # Raw counts are still displayed and guardrailed, but the optimizer also
    # compares each resident's exposure relative to that resident's exact monthly
    # target.  This prevents a resident with a smaller target (e.g. justified
    # absence / senior adjustment) from being forced to carry the same absolute
    # number of every post as a full-target resident while still keeping equal
    # exposure for equal targets.
    normalized_post_spread_vars: Dict[str, Tuple[int,int]] = {}
    # Two minimax guards are optimized before the sum of per-post spreads:
    #   1) RAW worst post spread — this is what people actually see in the matrix
    #      and what the <=2 generation-quality gate enforces;
    #   2) target-normalized worst post spread — protects proportional exposure
    #      when targets legitimately differ (senior/absence adjustments).
    # This prevents a weighted-sum pathology where eight tidy posts could "pay"
    # for one horrible outlier post.
    worst_raw_post_spread = mb.var(
        "worst_raw_monthly_post_spread",
        cost=12000000.0,
        lb=0.0,
        ub=max(1.0,float(calendar.monthrange(year,month)[1])*2.0),
        integer=False,
    )
    worst_normalized_post_spread = mb.var(
        "worst_normalized_monthly_post_spread",
        cost=8000000.0,
        lb=0.0,
        ub=10.0,
        integer=False,
    )

    def add_normalized_post_spread(cat: str):
        zmax=mb.var(f"normalized_rotation_{cat}_max",cost=0.0,lb=0.0,ub=10.0,integer=False)
        zmin=mb.var(f"normalized_rotation_{cat}_min",cost=0.0,lb=0.0,ub=10.0,integer=False)
        normalized_post_spread_vars[cat]=(zmax,zmin)
        for pi,p in enumerate(people):
            denom=max(1.0,float(targets.get(p.initials,0)))
            rc=rotation_count[(pi,cat)]
            mb.constraint(
                {rc:1.0/denom,zmax:-1.0},
                -np.inf,0.0,
                f"normalized post max {cat} {p.initials}"
            )
            mb.constraint(
                {rc:1.0/denom,zmin:-1.0},
                0.0,np.inf,
                f"normalized post min {cat} {p.initials}"
            )
        mb.constraint(
            {zmax:1.0,zmin:-1.0,worst_normalized_post_spread:-1.0},
            -np.inf,0.0,
            f"worst normalized post spread {cat}"
        )
        return zmax,zmin

    # BALANCED OPTIMIZATION — V2.5.26:
    # 1) HARD constraints / legal-rest / workload validity are absolute.
    # 2) GLOBAL FAIRNESS + FATIGUE rules define the good-schedule region:
    #    current-month workplace spread, weekend/workload/Friday/double spreads,
    #    long runs, fatigue after consecutive work and workplace diversity.
    # 3) ACTIVE INDIVIDUAL SOFT wishes are optimized inside that region.
    #    N/A contributes ZERO preference objective and acts as flexible capacity.
    #    A real wish matters, but one extra SOFT hit must not buy a gross fairness
    #    collapse elsewhere in the group.
    # 4) Historical fairness is audit-only and NEVER feeds the next month.
    #
    # V2.5.52 philosophy (implemented by the staged solve below):
    # TRUE ABSOLUTE HARD → CRITICAL SPS RO/SPS UG/WEEKEND/FRIDAY 0-1 → RESIDENT HARD
    # → critical temporal spacing → remaining burden → ordinary-post <=2
    # guardrail → vertically ranked SOFT → ordinary-post optimum + POST DEBT.

    MONTHLY_POST_SPREAD_WEIGHT = float(rule_value("monthly_post_spread_weight"))
    CUMULATIVE_POST_CATCHUP_WEIGHT = 0.0  # V2.5.96 retired: history never steers a future month
    # Explicit registry of all current-month post spread pairs. V2.5.52 later
    # separates them into a CRITICAL tier (SPS RO, SPS UG) and a bounded
    # NONCRITICAL tier; weekend exposure is modeled separately as a critical row.
    monthly_post_spread_pairs: Dict[str, Tuple[int,int]] = {}

    # Each category is balanced ACROSS residents separately. We never compare
    # unlike category volumes (e.g. Mamografijos supply vs CENTRO RO supply).
    for cat in ROTATION_CATEGORIES:
        add_normalized_post_spread(cat)
        # PRIMARY: current-month equality.
        raw_zmax,raw_zmin=add_spread_minimizer(
            f"monthly_rotation_{cat}",
            {pi:rotation_count[(pi,cat)] for pi in range(len(people))},
            weight=MONTHLY_POST_SPREAD_WEIGHT,
            ub=max(1,len(rotation_slots[cat]))
        )
        monthly_post_spread_pairs[cat]=(raw_zmax,raw_zmin)
        mb.constraint(
            {raw_zmax:1.0,raw_zmin:-1.0,worst_raw_post_spread:-1.0},
            -np.inf,0.0,
            f"worst raw post spread {cat}"
        )

        # SECONDARY / longitudinal catch-up: remember only what could not be
        # equalized this month and compensate it in later months.
        add_spread_minimizer(
            f"cumulative_rotation_{cat}",
            {pi:cumulative_rotation[(pi,cat)] for pi in range(len(people))},
            weight=CUMULATIVE_POST_CATCHUP_WEIGHT,
            ub=max([int(p.prior_rotation_counts.get(cat,0)) for p in people]+[0])
               + len(rotation_slots[cat]) + 200
        )

    add_spread_minimizer(
        "cumulative_weekend_fairness",
        cumulative_fair_weekend,
        weight=30.0,
        ub=max_prior_weekend + len(weekend_slots) + 20
    )
    add_spread_minimizer(
        "cumulative_holiday_fairness",
        cumulative_holiday,
        weight=0.0,
        ub=max_prior_holiday + len(holiday_slots) + 20
    )
    add_spread_minimizer(
        "cumulative_friday_fairness",
        cumulative_friday,
        weight=15.0,
        ub=max_prior_friday + len(friday_slots) + 40
    )
    add_spread_minimizer(
        "cumulative_double_fairness",
        cumulative_double,
        weight=10.0,
        ub=max_prior_double + ndays + 40
    )
    add_spread_minimizer(
        "cumulative_weekday_day_fairness",
        cumulative_weekday_day,
        weight=6.0,
        ub=max_prior_weekday_day + weekday_count(year, month) + 40
    )

    # Current-month smoothing. These do not override cumulative repair.
    add_spread_minimizer(
        "monthly_weekend_fairness",
        fairness_weekend_count,
        weight=220.0,
        ub=max(1, len(weekend_slots))
    )
    add_spread_minimizer(
        "monthly_holiday_fairness",
        holiday_count,
        weight=0.0,
        ub=max(1, len(holiday_slots))
    )
    add_spread_minimizer(
        "weekday_assignment_fairness",
        weekday_assignment_count,
        weight=160.0,
        ub=len(weekday_slots)
    )
    friday_spread_pair=add_spread_minimizer(
        "monthly_friday_fairness",
        friday_count,
        weight=90.0,
        ub=len(friday_slots)
    )
    fzmax,fzmin=friday_spread_pair
    mb.constraint(
        {fzmax:1.0,fzmin:-1.0},-np.inf,1.0,
        "V2577 ABSOLUTE SYSTEM Friday raw spread <=1"
    )
    double_spread_pair=add_spread_minimizer(
        "monthly_double_fairness",
        double_count,
        weight=70.0,
        ub=ndays
    )
    # V2.5.97: double equality is the neutral baseline, not an absolute blocker.
    # Active work-style wishes may widen it after HARD/coverage/rest constraints.
    dzmax,dzmin=double_spread_pair
    add_spread_minimizer(
        "monthly_weekday_day_fairness",
        weekday_day_count,
        weight=50.0,
        ub=weekday_count(year, month)
    )

    monthly_sps_ro_fair_pair=add_spread_minimizer(
        "monthly_sps_ro_volunteer_adjusted",
        fairness_sps_ro_count,
        weight=0.0,
        ub=max(1,len(rotation_slots["SPS RO"]))
    )
    cumulative_sps_ro_fair_pair=add_spread_minimizer(
        "cumulative_sps_ro_volunteer_adjusted",
        cumulative_fair_sps_ro,
        weight=0.0,
        ub=max([int(p.prior_rotation_counts.get("SPS RO",0)) for p in people]+[0])+len(rotation_slots["SPS RO"])+20
    )

    # V2.5.52 TWO-TIER STRUCTURAL POST FAIRNESS, refined in V2.5.90.
    # SPS UG stays raw 0-1. SPS RO + weekends use volunteer-adjusted counts only
    # in the first no-history month; otherwise these equal the raw counts.
    # Noncritical posts: target 0-1, guarded at <=2 normally; <=3 only when
    # <=2 is infeasible after higher-ranked constraints.
    critical_spread_pairs={
        "SPS RO": monthly_sps_ro_fair_pair,
        "SPS UG": monthly_post_spread_pairs["SPS UG"],
        "WEEKENDS": fairness_spread_vars["monthly_weekend_fairness"],
    }
    worst_critical_spread=mb.var("worst_critical_structural_spread",cost=0.0,lb=0.0,ub=max(1.0,float(ndays)*2.0),integer=False)
    for label,(zmax,zmin) in critical_spread_pairs.items():
        mb.constraint({zmax:1.0,zmin:-1.0,worst_critical_spread:-1.0},-np.inf,0.0,f"V2552 critical worst spread {label}")

    worst_noncritical_post_spread=mb.var("worst_noncritical_post_spread",cost=0.0,lb=0.0,ub=max(1.0,float(ndays)*2.0),integer=False)
    for cat in NONCRITICAL_ROTATION_CATEGORIES:
        zmax,zmin=monthly_post_spread_pairs[cat]
        mb.constraint({zmax:1.0,zmin:-1.0,worst_noncritical_post_spread:-1.0},-np.inf,0.0,f"V2552 noncritical worst spread {cat}")

    # V2.5.50 VERTICAL SOFT RANKS + HORIZONTAL WATER-FILLING.
    # SOFT-1 = protect personal time/recovery (Noriu laisvos, avoid doubles).
    # SOFT-2 = positive placement (Pageidauju dirbti).
    # SOFT-3 = persistent work-style / overall schedule shape (weekday/weekend/dispersed/clustered).
    # Inside each row, the solver first raises the least-honored resident count,
    # then maximizes the remaining feasible total, with a small max-count tie-break.
    soft_tier_vars={}
    for tier in ("SOFT1","SOFT2","SOFT3"):
        active=[pi for pi,rec in soft_tier_expr[tier].items() if int(rec.get("count",0))>0]
        if not active:
            continue
        max_count=max(int(soft_tier_expr[tier][pi]["count"]) for pi in active)
        total_cap=sum(int(soft_tier_expr[tier][pi]["count"]) for pi in active)
        minv=mb.var(f"{tier}_waterfill_min_honored",cost=0.0,lb=0.0,ub=max_count,integer=False)
        maxv=mb.var(f"{tier}_waterfill_max_honored",cost=0.0,lb=0.0,ub=max_count,integer=False)
        totalv=mb.var(f"{tier}_waterfill_total_honored",cost=0.0,lb=0.0,ub=total_cap,integer=False)
        total_co={totalv:-1.0}; total_const=0.0
        for pi in active:
            rec=soft_tier_expr[tier][pi]
            expr=dict(rec["coeffs"]); const=float(rec["const"])
            co_min=dict(expr); co_min[minv]=co_min.get(minv,0.0)-1.0
            mb.constraint(co_min,-const,np.inf,f"{tier} waterfill min {people[pi].initials}")
            co_max=dict(expr); co_max[maxv]=co_max.get(maxv,0.0)-1.0
            mb.constraint(co_max,-np.inf,-const,f"{tier} waterfill max {people[pi].initials}")
            total_const += const
            for vidx,coef in expr.items():
                total_co[vidx]=total_co.get(vidx,0.0)+coef
        mb.constraint(total_co,-total_const,-total_const,f"{tier} waterfill total identity")
        soft_tier_vars[tier]={
            "active":active,"min":minv,"max":maxv,"total":totalv,
            "max_count":max_count,"total_cap":total_cap,
        }

    # V2.5.58 holiday cohort spread variables are created BEFORE staged solving
    # so all objective vectors retain a stable dimension.
    holiday_cohort_spread_pairs={}
    for cname,cohort in (
        ("prefer_work",[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)>0]),
        ("neutral",[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)==0]),
        ("prefer_rest",[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)<0]),
    ):
        if len(cohort)>=2:
            holiday_cohort_spread_pairs[cname]=add_spread_minimizer(
                f"holiday_cohort_{cname}_cumulative",
                {pi:cumulative_holiday[pi] for pi in cohort},
                weight=0.0,
                ub=max_prior_holiday+len(holiday_slots)+20
            )

    active_weekend_volunteers=[
        pi for pi in range(len(people))
        if baseline_weekend_volunteer_mode and weekend_volunteer_slots_by_pi.get(pi)
    ]
    weekend_volunteer_waterfill=None
    if active_weekend_volunteers:
        max_req=max(int(voluntary_weekend_request_cap.get(pi,0)) for pi in active_weekend_volunteers)
        total_cap=sum(int(voluntary_weekend_request_cap.get(pi,0)) for pi in active_weekend_volunteers)
        wv_min=mb.var(
            "baseline_weekend_volunteer_min_honored",
            cost=0.0,lb=0.0,ub=max_req,integer=False
        )
        wv_max=mb.var(
            "baseline_weekend_volunteer_max_honored",
            cost=0.0,lb=0.0,ub=max_req,integer=False
        )
        wv_total=mb.var(
            "baseline_weekend_volunteer_total_honored",
            cost=0.0,lb=0.0,ub=total_cap,integer=False
        )
        total_co={wv_total:-1.0}
        for pi in active_weekend_volunteers:
            vc=voluntary_weekend_count[pi]
            mb.constraint(
                {vc:1.0,wv_min:-1.0},0.0,np.inf,
                f"baseline weekend volunteer min {people[pi].initials}"
            )
            mb.constraint(
                {vc:1.0,wv_max:-1.0},-np.inf,0.0,
                f"baseline weekend volunteer max {people[pi].initials}"
            )
            total_co[vc]=total_co.get(vc,0.0)+1.0
        mb.constraint(total_co,0.0,0.0,"baseline weekend volunteer total identity")
        weekend_volunteer_waterfill={
            "active":active_weekend_volunteers,
            "min":wv_min,"max":wv_max,"total":wv_total,
            "total_cap":total_cap,"max_req":max_req,
        }

    # V2.5.53 STAGED SOLVE — CRITICAL EXPOSURE + WEEKLY RECOVERY + GOLDEN MIDDLE.
    # Strict vertical order:
    #   A) TRUE ABSOLUTE HARD + RESIDENT-HARD zero-loss feasibility
    #      (including <=48h/rolling7, >=1 free day/7 and every `Negaliu dirbti`),
    #   B) CRITICAL STRUCTURAL WATER-FILL: SPS UG raw + SPS RO/WEEKENDS
    #      volunteer-adjusted in the first no-history month; remaining burden 0-1,
    #   C) RESIDENT-HARD audit compatibility only (losses remain fixed at zero),
    #   C4) BASELINE unpopular-weekend volunteers: maximize willing work and
    #       water-fill among competing volunteers,
    #   D) CRITICAL temporal spacing (avoid clustered non-voluntary SPS/weekends),
    #   E) WEEKLY LOAD / RECOVERY WATER-FILL: aim around 40h, equalize calendar-week
    #      burden, avoid consecutive doubles; after two doubles next day PM/off,
    #   E3) HOLIDAY PREFERENCE WATER-FILL: prefer-work cohort first, neutral next,
    #       prefer-rest last; equalize current+cumulative SYSTEM holiday burden,
    #   F) remaining involuntary burden/fatigue fairness; freeze the neutral
    #      group total of double-days and keep resident double spread <=2,
    #   G) NONCRITICAL post CORE guardrail (normally <=2, <=3 only if <=2 infeasible),
    #   H) SOFT-1 -> SOFT-2 -> SOFT-3 horizontal water-fill,
    #   I) NONCRITICAL post OPTIMAL + longitudinal post-debt catch-up inside all locks.
    #
    # This is the agreed golden middle: critical exposure is protected now because
    # later compensation cannot undo short-term fatigue; ordinary post imbalance may
    # flex slightly for legitimate personal-time SOFT, but only inside a bounded
    # corridor and is then repaid through cumulative post catch-up.
    # Respect the caller's solve budget instead of silently forcing a very long
    # minimum run. Production calls use 150-180 s; a 45 s floor keeps small
    # regression tests useful while preserving the same proportional stage order.
    total_budget=max(45.0,float(time_limit))
    absolute_feas_limit=max(4.0,total_budget*0.12)
    critical_limit=max(7.0,total_budget*0.18)
    rh_min_limit=max(4.0,total_budget*0.10)
    rh_fair_limit=max(6.0,total_budget*0.12)
    weekend_volunteer_limit=max(4.0,total_budget*0.06)
    priority_colocation_limit=max(4.0,total_budget*0.05)
    temporal_limit=max(4.0,total_budget*0.07)
    weekly_load_limit=max(5.0,total_budget*0.09)
    holiday_limit=max(4.0,total_budget*0.06)
    fairness_limit=max(5.0,total_budget*0.07)
    noncrit_guard_limit=max(5.0,total_budget*0.07)
    soft_limit=max(6.0,total_budget*0.10)
    post_opt_limit=max(5.0,total_budget*0.06)

    full_costs=list(mb.c)
    # V2.5.107: no Resident-HARD penalty weights. `Negaliu dirbti` is already
    # hard-locked to zero violations at model construction, so later objectives
    # can only optimize fairness/SOFT within that mandatory feasible space.
    # Prefer necessary doubles to contain SPS RO / SPS UG rather than pairing two
    # ordinary posts. This is lower than safety/critical-count locks but stronger
    # than cosmetic placement.
    for v in noncritical_double_vars:
        full_costs[v] += 240.0

    def _spread_value(vec, pair):
        zmax,zmin=pair
        return max(0.0,float(vec[zmax])-float(vec[zmin]))

    def _actual_spread_from_count_vars(vec, count_vars):
        """Read the real max-min from exact count variables, never from loose auxiliaries.

        zmax/zmin variables are safe for constraints/objectives, but on a fallback
        incumbent where they were not optimized they may sit anywhere inside their
        bounds. Treating those loose auxiliary values as the achieved spread caused
        V2.5.62 to report/lock values such as 38/44 even when the visible matrix
        spread was only 3/4. The real count variables are equality-linked to x and
        therefore remain trustworthy on every incumbent.
        """
        vals=[float(vec[v]) for v in count_vars]
        return (max(vals)-min(vals)) if vals else 0.0

    def _critical_actual_spreads(vec):
        return {
            "SPS RO": _actual_spread_from_count_vars(vec,[fairness_sps_ro_count[pi] for pi in range(len(people))]),
            "SPS UG": _actual_spread_from_count_vars(vec,[rotation_count[(pi,"SPS UG")] for pi in range(len(people))]),
            "WEEKENDS": _actual_spread_from_count_vars(vec,[fairness_weekend_count[pi] for pi in range(len(people))]),
        }

    def _assignment_tiebreak(costs, scale=100000000.0):
        for (pi,sid),vidx in x.items():
            costs[vidx]+=(((pi+1)*41+(sid+1)*17)%109)/scale

    # Stage A — any TRUE ABSOLUTE-HARD-valid schedule.
    absolute_feas_costs=[0.0 for _ in mb.c]
    _assignment_tiebreak(absolute_feas_costs,1000000.0)
    mb.c=absolute_feas_costs
    absolute_feas_res=mb.solve(time_limit=absolute_feas_limit)
    if absolute_feas_res.x is None:
        fmsg=str(getattr(absolute_feas_res,"message","No ABSOLUTE-HARD feasible solution"))
        return SolveResult(
            False,
            "MANDATORY FEASIBILITY FAILED: safety / coverage / exact workload and all `Negaliu dirbti` blocks could not be satisfied in this solve. No SYSTEM draft was returned. Solverio būsena: "+fmsg,
            targets=targets,
            request_snapshot=request_snapshot,
        )

    # Stage B1 — VERIFIED CRITICAL FAIRNESS CORRIDOR.
    #
    # V2.5.63 fail-safe: never widen SPS RO / SPS UG / weekend equality merely
    # because a short timed solve failed to return an incumbent. We test corridors
    # in ascending order. A wider corridor is allowed only after the tighter one is
    # PROVEN infeasible (HiGHS status 2). A timeout with no incumbent is not proof
    # of infeasibility: retry once, then fail the generation instead of emitting a
    # visibly unfair 4-vs-1 SYSTEM schedule.
    critical_candidate=None
    critical_best_worst=None
    critical_01_proven_or_found=False
    critical_01_trial_status="UNTESTED"
    critical_explicit_trial_used=True
    critical_search_log=[]

    # 0 cannot be feasible whenever a critical slot total is not divisible by the
    # resident count; 1 is therefore the constitutional first corridor.
    max_critical_cap=max(4, int(math.ceil(float(len(weekend_slots)+len(rotation_slots["SPS RO"])+len(rotation_slots["SPS UG"]))/max(1,len(people)))))
    corridor_caps=list(range(CRITICAL_SPREAD_TARGET, max_critical_cap+1))
    per_corridor=max(6.0,critical_limit/max(1,min(3,len(corridor_caps))))

    for cap in corridor_caps:
        row_mark=len(mb.rows)
        for label,(zmax,zmin) in critical_spread_pairs.items():
            mb.constraint({zmax:1.0,zmin:-1.0},-np.inf,float(cap),f"V2563 verified critical corridor <= {cap} {label}")
        # For the constitutional 0-1 corridor, integer totals make the exact
        # floor/ceil entitlement band known in advance. Adding these direct
        # count bounds is equivalent to spread<=1 but gives HiGHS a much tighter
        # search space than loose zmax/zmin auxiliaries.
        if int(cap)==1 and len(people)>0:
            for cat in CRITICAL_ROTATION_CATEGORIES:
                if baseline_weekend_volunteer_mode and cat=="SPS RO":
                    # Adjusted fair supply is endogenous; spread constraint above is exact.
                    continue
                total_cat=len(rotation_slots[cat])
                lo=total_cat//len(people); hi=int(math.ceil(total_cat/len(people)))
                for pi,p in enumerate(people):
                    mb.constraint({rotation_count[(pi,cat)]:1.0},float(lo),float(hi),f"V2563 direct 0-1 {cat} entitlement {p.initials}")
            if not baseline_weekend_volunteer_mode:
                total_weekend=len(weekend_slots)
                wlo=total_weekend//len(people); whi=int(math.ceil(total_weekend/len(people)))
                for pi,p in enumerate(people):
                    mb.constraint({weekend_count[pi]:1.0},float(wlo),float(whi),f"V2563 direct 0-1 weekend entitlement {p.initials}")
        trial_costs=[0.0 for _ in mb.c]
        _assignment_tiebreak(trial_costs,1000000.0)
        mb.c=trial_costs
        trial=mb.solve(time_limit=per_corridor)
        status=int(getattr(trial,"status",99))
        critical_search_log.append({"cap":int(cap),"status":status,"incumbent":bool(trial.x is not None)})

        if trial.x is not None:
            critical_candidate=trial
            critical_best_worst=int(cap)
            critical_01_proven_or_found=bool(cap<=CRITICAL_SPREAD_TARGET)
            critical_01_trial_status="FOUND_VERIFIED_0_1" if cap<=CRITICAL_SPREAD_TARGET else f"FOUND_VERIFIED_{cap}"
            # Keep the successful corridor rows.
            break

        # No incumbent. Only a mathematically proven infeasible corridor may be
        # relaxed. A time-limit/unknown result gets a second focused attempt.
        if status != 2:
            retry=mb.solve(time_limit=max(10.0,per_corridor*1.5))
            rstatus=int(getattr(retry,"status",99))
            critical_search_log.append({"cap":int(cap),"status":rstatus,"incumbent":bool(retry.x is not None),"retry":True})
            if retry.x is not None:
                critical_candidate=retry
                critical_best_worst=int(cap)
                critical_01_proven_or_found=bool(cap<=CRITICAL_SPREAD_TARGET)
                critical_01_trial_status="FOUND_VERIFIED_0_1_RETRY" if cap<=CRITICAL_SPREAD_TARGET else f"FOUND_VERIFIED_{cap}_RETRY"
                break
            if rstatus != 2:
                del mb.rows[row_mark:]
                return SolveResult(
                    False,
                    f"Nepavyko per skirtą laiką patvirtinti, kad SPS RO, SPS UG ir savaitgaliai paskirstyti pakankamai lygiai (leistinas skirtumas <= {cap}). Grafikas sąmoningai negrąžintas. Paleiskite generavimą dar kartą.",
                    targets=targets,
                    request_snapshot=request_snapshot,
                )
        # Proven infeasible: remove this corridor and try the next wider one.
        del mb.rows[row_mark:]

    if critical_candidate is None or critical_best_worst is None:
        return SolveResult(
            False,
            "Nepavyko rasti patvirtinto pakankamai lygaus SPS RO / SPS UG / savaitgalių paskirstymo. Grafikas negrąžintas.",
            targets=targets,
            request_snapshot=request_snapshot,
        )

    crit_candidate=critical_candidate
    crit_spreads=_critical_actual_spreads(crit_candidate.x)

    # The successful corridor rows are already hard constraints. Also lock the
    # auxiliary worst variable for downstream compatibility, but measure/report
    # the achieved values from the real count variables.
    mb.constraint({worst_critical_spread:1.0},-np.inf,float(critical_best_worst),"V2563 verified critical worst spread lock")

    # Stage B2 — within the critical minimax frontier minimize the sum of the three
    # spreads, then cumulative weekend/SPS imbalance and first-exposure breadth.
    critical_fill_costs=[0.0 for _ in mb.c]
    for label,(zmax,zmin) in critical_spread_pairs.items():
        critical_fill_costs[zmax]+=1000000.0; critical_fill_costs[zmin]-=1000000.0
    # Cumulative catch-up for the critical trio.
    cwmax,cwmin=fairness_spread_vars["cumulative_weekend_fairness"]
    critical_fill_costs[cwmax]+=400.0; critical_fill_costs[cwmin]-=400.0
    for cat in CRITICAL_ROTATION_CATEGORIES:
        if cat=="SPS RO":
            czmax,czmin=cumulative_sps_ro_fair_pair
        else:
            czmax,czmin=fairness_spread_vars[f"cumulative_rotation_{cat}"]
        critical_fill_costs[czmax]+=300.0; critical_fill_costs[czmin]-=300.0
        for pi in range(len(people)):
            critical_fill_costs[rotation_used[(pi,cat)]]-=20.0
    _assignment_tiebreak(critical_fill_costs,1000000000.0)
    mb.c=critical_fill_costs
    crit_fill_fraction=0.30 if critical_explicit_trial_used else 0.52
    crit_fill_res=mb.solve(time_limit=max(4.0,critical_limit*crit_fill_fraction))
    critical_structural_res=crit_fill_res if crit_fill_res.x is not None else crit_candidate
    critical_spreads_locked={k:int(round(v)) for k,v in _critical_actual_spreads(critical_structural_res.x).items()}
    # Keep the verified per-category corridor as the hard frontier while also
    # tightening the auxiliary max/min variables. We deliberately lock only the
    # corridor CAP (e.g. at most 1+1+1), not the exact timed incumbent sum, so
    # concrete dates remain flexible for Resident-HARD/SOFT placement.
    critical_total_lock=int(critical_best_worst*len(critical_spread_pairs))
    critical_total_expr={}
    for zmax,zmin in critical_spread_pairs.values():
        critical_total_expr[zmax]=critical_total_expr.get(zmax,0.0)+1.0
        critical_total_expr[zmin]=critical_total_expr.get(zmin,0.0)-1.0
    mb.constraint(critical_total_expr,-np.inf,float(critical_total_lock),"V2563 critical corridor auxiliary cap")

    # Stage C1 — RESIDENT HARD zero-loss verification. The zero-loss rule was hard-locked before every fairness stage.
    rh_min_costs=[0.0 for _ in mb.c]
    rh_min_costs[resident_hard_total_loss]=1000000.0
    _assignment_tiebreak(rh_min_costs,100000.0)
    mb.c=rh_min_costs
    rh_min_res=mb.solve(time_limit=rh_min_limit)
    rh_min_candidate=rh_min_res if rh_min_res.x is not None else critical_structural_res
    resident_hard_min_total=int(round(max(0.0,float(rh_min_candidate.x[resident_hard_total_loss]))))
    rh_minimum_proven=bool(resident_hard_min_total==0)
    if resident_hard_min_total!=0:
        return SolveResult(False,"RESIDENT HARD ZERO-LOSS GATE FAILED — no SYSTEM draft returned.",targets=targets,request_snapshot=request_snapshot)
    mb.constraint({resident_hard_total_loss:1.0},0.0,0.0,"V25107 resident-hard zero-loss proof lock")

    # Stage C2 — current-month horizontal progressive filling.
    rh_current_costs=[0.0 for _ in mb.c]
    if rh_min_honored is not None:
        rh_current_costs[rh_min_honored]=-1000000.0
        rh_current_costs[rh_max_honored]=1.0
    else:
        rh_current_costs[rh_current_max]=1.0
    _assignment_tiebreak(rh_current_costs,1000000.0)
    mb.c=rh_current_costs
    rh_current_res=mb.solve(time_limit=max(6.0,rh_fair_limit*0.52))
    current_fair_res=rh_current_res if rh_current_res.x is not None else rh_min_candidate
    if rh_min_honored is not None and rh_current_res.x is not None:
        rh_min_lock=max(0.0,float(current_fair_res.x[rh_min_honored]))
        rh_max_lock=max(0.0,float(current_fair_res.x[rh_max_honored]))
        mb.constraint({rh_min_honored:1.0},rh_min_lock-1e-6,np.inf,"V2552 resident-hard waterfill minimum lock")
        mb.constraint({rh_max_honored:1.0},-np.inf,rh_max_lock+1e-6,"V2552 resident-hard waterfill maximum lock")
    resident_hard_current_max_lock=int(math.ceil(max(0.0,float(current_fair_res.x[rh_current_max]))-1e-7))

    # Stage C3 — backward-compatible Resident-HARD audit metrics only; V2.5.107 never rotates or compensates mandatory-unavailability violations.
    rh_history_costs=[0.0 for _ in mb.c]
    rh_history_costs[rh_cumulative_max]=1000000.0
    rh_history_costs[rh_cumulative_min]=-1000000.0
    rh_history_costs[rh_current_min]=-10000.0
    _assignment_tiebreak(rh_history_costs,10000000.0)
    mb.c=rh_history_costs
    rh_history_res=mb.solve(time_limit=max(6.0,rh_fair_limit*0.48))
    feasibility_res=rh_history_res if rh_history_res.x is not None else current_fair_res
    resident_hard_cumulative_spread_lock=int(math.ceil(max(0.0,float(feasibility_res.x[rh_cumulative_max])-float(feasibility_res.x[rh_cumulative_min]))-1e-7))
    mb.constraint({rh_cumulative_max:1.0,rh_cumulative_min:-1.0},-np.inf,float(resident_hard_cumulative_spread_lock),"V2552 resident-hard historical spread lock")

    if priority_colocation_week_vars:
        _pc_costs=[0.0 for _ in mb.c]
        for wv in priority_colocation_week_vars:
            _pc_costs[wv]=-1.0
        _assignment_tiebreak(_pc_costs,1000000000.0)
        mb.c=_pc_costs
        _pc_res=mb.solve(time_limit=priority_colocation_limit)
        if _pc_res.x is not None:
            feasibility_res=_pc_res
            _pc_total=int(round(sum(float(_pc_res.x[wv]) for wv in priority_colocation_week_vars)))
            mb.constraint({wv:1.0 for wv in priority_colocation_week_vars},float(_pc_total),float(_pc_total),"priority coloc optimum lock")

    # Stage C4 — BASELINE UNPOPULAR-WEEKEND VOLUNTEERS.
    # Safety/coverage and Resident-HARD are already protected. Now explicitly
    # maximize willing weekend work BEFORE temporal spacing / 40h shaping.
    # Multiple volunteers are water-filled: first raise the least-honored volunteer,
    # then maximize total honored volunteer assignments.
    weekend_volunteer_locks={}
    if weekend_volunteer_waterfill is not None:
        wv=weekend_volunteer_waterfill
        volunteer_costs=[0.0 for _ in mb.c]
        volunteer_costs[wv["min"]]=-(float(wv["total_cap"])+1.0)
        volunteer_costs[wv["total"]]=-1.0
        volunteer_costs[wv["max"]]=1.0/max(10.0,float(wv["total_cap"])+1.0)
        _assignment_tiebreak(volunteer_costs,1000000000.0)
        mb.c=volunteer_costs
        wvr=mb.solve(time_limit=weekend_volunteer_limit)
        if wvr.x is not None:
            feasibility_res=wvr
            floor=max(0.0,float(wvr.x[wv["min"]]))
            total=max(0.0,float(wvr.x[wv["total"]]))
            ceiling=max(0.0,float(wvr.x[wv["max"]]))
            mb.constraint({wv["min"]:1.0},floor-1e-6,np.inf,"V2590 baseline weekend volunteer minimum lock")
            mb.constraint({wv["total"]:1.0},total-1e-6,np.inf,"V2590 baseline weekend volunteer total lock")
            mb.constraint({wv["max"]:1.0},-np.inf,ceiling+1e-6,"V2590 baseline weekend volunteer maximum lock")
            weekend_volunteer_locks={
                "min":round(floor,6),
                "total":round(total,6),
                "max":round(ceiling,6),
                "active":len(wv["active"]),
                "requested_assignment_slots":int(wv["total_cap"]),
            }

    # Stage D — critical temporal spacing. Count fairness is already locked, so
    # this can only decide WHEN equivalent critical exposure is placed.
    critical_temporal_lock=None
    temporal_res=feasibility_res
    if critical_temporal_penalty_vars:
        temporal_costs=[0.0 for _ in mb.c]
        temporal_expr={}
        for vidx,w in critical_temporal_penalty_weights.items():
            temporal_costs[vidx]+=float(w)
            temporal_expr[vidx]=temporal_expr.get(vidx,0.0)+float(w)
        _assignment_tiebreak(temporal_costs,1000000000.0)
        mb.c=temporal_costs
        tr=mb.solve(time_limit=temporal_limit)
        if tr.x is not None:
            temporal_res=tr
            critical_temporal_lock=float(sum(float(w)*float(tr.x[v]) for v,w in critical_temporal_penalty_weights.items()))
            mb.constraint(temporal_expr,-np.inf,critical_temporal_lock+1e-6,"V2552 critical temporal spacing lock")

    # Stage E — WEEKLY LOAD + RECOVERY WATER-FILL. Higher-rank count fairness
    # (critical SPS/weekends + Resident-HARD) is already locked. Now distribute
    # temporal workload so nobody gets a 60h first week while peers are light.
    #
    # E1 minimizes the WORST rolling-7 excess above the 40h planning target.
    # E2 then minimizes total >40h exposure, week-to-week resident spread and
    # consecutive-double recovery burden inside that worst-case frontier.
    weekly_load_res=temporal_res
    weekly_max_over40_lock=None
    weekly_total_over40_lock=None
    weekly_worst_calendar_spread_lock=None
    weekly_recovery_penalty_lock=None

    weekly_peak_costs=[0.0 for _ in mb.c]
    weekly_peak_costs[max_rolling7_over40]=1000000.0
    _assignment_tiebreak(weekly_peak_costs,100000000.0)
    mb.c=weekly_peak_costs
    wr1=mb.solve(time_limit=max(4.0,weekly_load_limit*0.45))
    if wr1.x is not None:
        weekly_load_res=wr1
        weekly_max_over40_lock=max(0.0,float(wr1.x[max_rolling7_over40]))
        mb.constraint(
            {max_rolling7_over40:1.0},-np.inf,weekly_max_over40_lock+1e-6,
            "V2553 weekly worst over40 lock"
        )

    weekly_shape_costs=[0.0 for _ in mb.c]
    weekly_shape_costs[total_rolling7_over40]=5000.0
    weekly_shape_costs[worst_calendar_week_spread]=1200.0
    for zmax,zmin in calendar_week_spread_pairs.values():
        weekly_shape_costs[zmax]+=120.0
        weekly_shape_costs[zmin]-=120.0
    for v in consecutive_double_pair_vars:
        weekly_shape_costs[v]+=900.0
    for v in post_two_double_work_vars:
        # OFF is preferred after two doubles; PM-only remains feasible.
        weekly_shape_costs[v]+=1400.0
    _assignment_tiebreak(weekly_shape_costs,1000000000.0)
    mb.c=weekly_shape_costs
    wr2=mb.solve(time_limit=max(5.0,weekly_load_limit*0.55))
    if wr2.x is not None:
        weekly_load_res=wr2
        weekly_total_over40_lock=max(0.0,float(wr2.x[total_rolling7_over40]))
        weekly_worst_calendar_spread_lock=max(0.0,float(wr2.x[worst_calendar_week_spread]))
        recovery_expr={}
        recovery_value=0.0
        for v in consecutive_double_pair_vars:
            recovery_expr[v]=recovery_expr.get(v,0.0)+1.0
            recovery_value+=float(wr2.x[v])
        for v in post_two_double_work_vars:
            recovery_expr[v]=recovery_expr.get(v,0.0)+2.0
            recovery_value+=2.0*float(wr2.x[v])
        weekly_recovery_penalty_lock=max(0.0,recovery_value)
        mb.constraint({total_rolling7_over40:1.0},-np.inf,weekly_total_over40_lock+1e-6,"V2553 weekly total over40 lock")
        mb.constraint({worst_calendar_week_spread:1.0},-np.inf,weekly_worst_calendar_spread_lock+1e-6,"V2553 weekly calendar spread lock")
        if recovery_expr:
            mb.constraint(recovery_expr,-np.inf,weekly_recovery_penalty_lock+1e-6,"V2553 double recovery shape lock")

    # Stage E3 — PUBLIC-HOLIDAY PREFERENCE + FAIRNESS WATER-FILL (V2.5.58).
    # This layer is solved only after ABSOLUTE HARD, critical SPS/weekend count
    # equality, Resident-HARD, spacing and weekly-recovery are locked. Therefore
    # holiday wishes can choose among safe/equally-fair candidates but cannot buy
    # a worse critical SPS/weekend spread or unsafe weekly load.
    holiday_res=weekly_load_res
    holiday_locks={}
    if holiday_slots:
        prefer_work=[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)>0]
        prefer_rest=[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)<0]
        neutral=[pi for pi,p in enumerate(people) if int(getattr(p,"holiday_preference",0) or 0)==0]

        # 1) Minimize holiday work assigned to residents who explicitly prefer rest.
        if prefer_rest:
            rest_costs=[0.0 for _ in mb.c]
            for pi in prefer_rest: rest_costs[holiday_count[pi]]+=1000000.0
            _assignment_tiebreak(rest_costs,100000000.0)
            mb.c=rest_costs
            hr=mb.solve(time_limit=max(3.0,holiday_limit*0.30))
            if hr.x is not None:
                holiday_res=hr
                rest_total=sum(float(hr.x[holiday_count[pi]]) for pi in prefer_rest)
                mb.constraint({holiday_count[pi]:1.0 for pi in prefer_rest},-np.inf,rest_total+1e-6,"V2558 holiday rest-preference lock")
                holiday_locks["prefer_rest_total"]=round(rest_total,6)

        # 2) Inside that lock, maximize duty going to residents who WANT holidays.
        if prefer_work:
            work_costs=[0.0 for _ in mb.c]
            for pi in prefer_work: work_costs[holiday_count[pi]]-=1000000.0
            _assignment_tiebreak(work_costs,100000000.0)
            mb.c=work_costs
            hw=mb.solve(time_limit=max(3.0,holiday_limit*0.25))
            if hw.x is not None:
                holiday_res=hw
                work_total=sum(float(hw.x[holiday_count[pi]]) for pi in prefer_work)
                mb.constraint({holiday_count[pi]:1.0 for pi in prefer_work},work_total-1e-6,np.inf,"V2558 holiday willing-work total lock")
                holiday_locks["prefer_work_total"]=round(work_total,6)

        # 3) Water-fill current + cumulative holiday burden within each cohort.
        # Variables were created before staged solving to keep the MILP dimension stable.
        cohort_costs=[0.0 for _ in mb.c]
        for cname,weight in (("prefer_work",50000.0),("neutral",5000.0),("prefer_rest",500.0)):
            pair=holiday_cohort_spread_pairs.get(cname)
            if pair is None:
                continue
            hmax,hmin=pair
            cohort_costs[hmax]+=weight
            cohort_costs[hmin]-=weight
        # When no stronger preference/fairness distinction exists, slightly favor
        # lower current monthly workload for neutral holiday coverage.
        for pi in neutral:
            for d in range(1,ndays+1):
                # workday variables are a tiny tie-break, never a higher-rank trade.
                cohort_costs[workday[(pi,d)]]+=0.0001
        _assignment_tiebreak(cohort_costs,1000000000.0)
        mb.c=cohort_costs
        hb=mb.solve(time_limit=max(3.0,holiday_limit*0.45))
        if hb.x is not None:
            holiday_res=hb

    # Stage F — remaining involuntary burden/fatigue fairness, deliberately
    # excluding NONCRITICAL post perfection and all individual SOFT. Weekly load
    # and recovery are already locked, so later preferences cannot recreate a
    # 60h week or a double-double-double sequence.
    fairness_costs=list(full_costs)
    for vidx,delta in preference_cost_delta.items():
        fairness_costs[vidx]-=delta
    fairness_costs[worst_raw_post_spread]=0.0
    fairness_costs[worst_normalized_post_spread]=0.0
    fairness_costs[worst_noncritical_post_spread]=0.0
    for cat in NONCRITICAL_ROTATION_CATEGORIES:
        zmax,zmin=monthly_post_spread_pairs[cat]
        fairness_costs[zmax]=0.0; fairness_costs[zmin]=0.0
        czmax,czmin=fairness_spread_vars[f"cumulative_rotation_{cat}"]
        fairness_costs[czmax]=0.0; fairness_costs[czmin]=0.0
        for pi in range(len(people)):
            fairness_costs[rotation_used[(pi,cat)]]=0.0
    mb.c=fairness_costs
    fairness_res=mb.solve(time_limit=fairness_limit)
    if fairness_res.x is None:
        fairness_res=holiday_res
    guardrails_established=fairness_res.x is not None
    fairness_guardrails={}
    waterfill_locks={}
    # V2.5.71: work-style preferences are allocation preferences, not a licence to
    # create more (or fewer) double-days for the group. Freeze the preference-free
    # neutral baseline total before SOFT stages; only redistribution is allowed.
    neutral_total_doubles=None
    if fairness_res.x is not None:
        neutral_total_doubles=int(round(sum(float(fairness_res.x[double_count[pi]]) for pi in range(len(people)))))
        mb.constraint(
            {double_count[pi]:1.0 for pi in range(len(people))},
            float(neutral_total_doubles),float(neutral_total_doubles),
            "V2571 neutral total doubles lock"
        )

    # Lock only the non-post burden baseline (+ normal general tolerance). Critical
    # exposure already has exact higher-rank locks; ordinary post spread is handled
    # by the separate <=2/<=3 corridor below.
    if guardrails_established:
        for name,(zmax,zmin) in fairness_spread_vars.items():
            if name not in {"monthly_double_fairness","monthly_friday_fairness","monthly_weekday_day_fairness"}:
                continue
            achieved=max(0.0,float(fairness_res.x[zmax])-float(fairness_res.x[zmin]))
            baseline=int(math.ceil(achieved-1e-7))
            tolerance=int(rule_value("general_guardrail_tolerance"))
            ceiling=baseline+tolerance
            mb.constraint({zmax:1.0,zmin:-1.0},-np.inf,float(ceiling),f"V2552 burden guardrail {name}")
            fairness_guardrails[name]={"baseline_spread":baseline,"tolerance":tolerance,"ceiling":ceiling}

    # Stage G — VERIFIED NONCRITICAL corridor.
    # Normal target <=2. <=3 is allowed only if <=2 is PROVEN infeasible. A
    # time-limit with no incumbent is never treated as evidence that a 4-vs-1 or
    # 5-vs-0 distribution is necessary. If the solver cannot verify the corridor,
    # generation stops and asks for a retry instead of returning an unfair draft.
    noncritical_guardrail_ceiling=None
    noncritical_guardrail_status="UNTESTED"
    noncritical_search_log=[]
    noncrit_base_res=fairness_res
    for candidate_ceiling,label in ((NONCRITICAL_SPREAD_NORMAL_CEILING,"STRUCTURAL_WATERFILL_0_1"),(NONCRITICAL_SPREAD_EXCEPTIONAL_CEILING,"PROVEN_EXCEPTION_0_2"),(NONCRITICAL_SPREAD_LAST_RESORT_CEILING,"PROVEN_LAST_RESORT_0_3")):
        mark=len(mb.rows)
        for cat in NONCRITICAL_ROTATION_CATEGORIES:
            zmax,zmin=monthly_post_spread_pairs[cat]
            mb.constraint({zmax:1.0,zmin:-1.0},-np.inf,float(candidate_ceiling),f"V2563 verified noncritical {label} {cat}")
        feas_costs=[0.0 for _ in mb.c]
        _assignment_tiebreak(feas_costs,1000000.0)
        mb.c=feas_costs
        nr=mb.solve(time_limit=max(7.0,noncrit_guard_limit/2.0))
        nstatus=int(getattr(nr,"status",99))
        noncritical_search_log.append({"ceiling":int(candidate_ceiling),"status":nstatus,"incumbent":bool(nr.x is not None)})
        if nr.x is not None:
            noncritical_guardrail_ceiling=int(candidate_ceiling)
            noncritical_guardrail_status=label
            noncrit_base_res=nr
            break
        if nstatus != 2:
            # Retry the SAME corridor. Do not silently relax <=2 to <=3 just
            # because a short solve timed out.
            nr2=mb.solve(time_limit=max(12.0,noncrit_guard_limit))
            nstatus2=int(getattr(nr2,"status",99))
            noncritical_search_log.append({"ceiling":int(candidate_ceiling),"status":nstatus2,"incumbent":bool(nr2.x is not None),"retry":True})
            if nr2.x is not None:
                noncritical_guardrail_ceiling=int(candidate_ceiling)
                noncritical_guardrail_status=label+"_RETRY"
                noncrit_base_res=nr2
                break
            if nstatus2 != 2:
                del mb.rows[mark:]
                return SolveResult(
                    False,
                    f"Nepavyko per skirtą laiką patvirtinti pakankamai lygaus kitų darbo vietų paskirstymo (leistinas skirtumas <= {candidate_ceiling}). Grafikas sąmoningai negrąžintas. Paleiskite generavimą dar kartą.",
                    targets=targets,
                    request_snapshot=request_snapshot,
                )
        # Proven infeasible corridor: only now may the next wider level be tried.
        del mb.rows[mark:]

    if noncritical_guardrail_ceiling is None:
        return SolveResult(
            False,
            "Net ir po svarbesnių taisyklių neįmanoma išlaikyti priimtino darbo vietų paskirstymo. Grafikas negrąžintas; reikia peržiūrėti privalomus apribojimus, o ne priimti labai nelygų SYSTEM grafiką.",
            targets=targets,
            request_snapshot=request_snapshot,
        )

    # Stage H — strict vertical SOFT water-filling. Because the critical trio is
    # locked and ordinary posts are merely bounded, legitimate SOFT can use the
    # small 0-2 flexibility without creating a critical fatigue/exposure outlier.
    tier_res=noncrit_base_res
    active_tiers=[t for t in ("SOFT1","SOFT2","SOFT3") if t in soft_tier_vars]
    per_tier_limit=max(4.0,soft_limit/max(1,len(active_tiers)))
    for tier in active_tiers:
        tv=soft_tier_vars[tier]
        tier_costs=[0.0 for _ in mb.c]
        tier_costs[tv["min"]]=-(float(tv["total_cap"])+1.0)
        tier_costs[tv["total"]]=-1.0
        tier_costs[tv["max"]]=1.0/max(10.0,float(tv["total_cap"])+1.0)
        _assignment_tiebreak(tier_costs,100000000.0)
        mb.c=tier_costs
        tr=mb.solve(time_limit=per_tier_limit)
        if tr.x is None:
            continue
        tier_res=tr
        floor=max(0.0,float(tr.x[tv["min"]])); total=max(0.0,float(tr.x[tv["total"]])); ceiling=max(0.0,float(tr.x[tv["max"]]))
        mb.constraint({tv["min"]:1.0},floor-1e-6,np.inf,f"V2552 {tier} minimum entitlement lock")
        mb.constraint({tv["total"]:1.0},total-1e-6,np.inf,f"V2552 {tier} total fulfilment lock")
        mb.constraint({tv["max"]:1.0},-np.inf,ceiling+1e-6,f"V2552 {tier} maximum entitlement lock")
        waterfill_locks[tier]={"min":round(floor,6),"total":round(total,6),"max":round(ceiling,6),"active":len(tv["active"])}

    # Stage I — now optimize NONCRITICAL post spread and explicit longitudinal
    # catch-up (post debt) WITHOUT sacrificing any locked SOFT result.
    post_opt_costs=[0.0 for _ in mb.c]
    post_opt_costs[worst_noncritical_post_spread]=10000000.0
    for _bv in onko_zero_mammo_bonus_vars:
        post_opt_costs[_bv]-=2000.0
    for cat in NONCRITICAL_ROTATION_CATEGORIES:
        zmax,zmin=monthly_post_spread_pairs[cat]
        post_opt_costs[zmax]+=100000.0; post_opt_costs[zmin]-=100000.0
        czmax,czmin=fairness_spread_vars[f"cumulative_rotation_{cat}"]
        post_opt_costs[czmax]+=500.0; post_opt_costs[czmin]-=500.0
        for pi in range(len(people)):
            post_opt_costs[rotation_used[(pi,cat)]]-=20.0
    _assignment_tiebreak(post_opt_costs,1000000000.0)
    mb.c=post_opt_costs
    post_opt_res=mb.solve(time_limit=max(6.0,post_opt_limit))
    if post_opt_res.x is not None:
        res=post_opt_res
        solve_stage="V2598_CRITICAL_01_RH_WEEKLY_RECOVERY_SOFT_MONTHLY_OPT"
    else:
        res=tier_res
        solve_stage="V2553_TIER_FALLBACK"

    # Compatibility diagnostics used by existing UI/export code.
    post_fill_res=crit_fill_res
    post_system_worst_lock=int(critical_best_worst)
    post_system_total_lock=int(critical_total_lock)
    post_system_spreads={cat:int(round(_actual_spread_from_count_vars(res.x,[rotation_count[(pi,cat)] for pi in range(len(people))]))) for cat in ROTATION_CATEGORIES}
    assignments: Dict[int, str] = {}
    for pi, p in enumerate(people):
        for s in slots:
            if res.x[x[(pi, s.idx)]] > 0.5:
                assignments[s.idx] = p.initials

    if solve_stage=="LOCAL_FAIRNESS_FALLBACK":
        assignments,stats,accepted_repairs=local_fairness_repair(
            year,month,people,assignments,targets,
            seconds=min(12.0,max(5.0,total_budget*0.10))
        )
    else:
        stats = validate_schedule(year, month, people, slots, assignments, targets)
        accepted_repairs=0

    # V2.5.52 uses explicit staged critical/noncritical corridors; do not run the
    # old V2.5.48 all-post <=2 rescue/local swap layer, because it could silently
    # undo the new lexicographic locks or reject an explicitly diagnosed <=3
    # noncritical exceptional case.
    post_ceiling_rescue_attempted=False
    post_ceiling_rescue_succeeded=False
    quality_repairs=0

    stats["global"]["gap_plan"] = gap_plan
    stats["global"]["planned_gap_count"] = gap_plan.get("planned_gap_count",0)
    stats["global"]["preference_normalization"] = preference_normalization
    stats["global"]["preference_normalization_count"] = len(preference_normalization)
    stats["global"]["fairness_guardrails"] = fairness_guardrails
    stats["global"]["fairness_guardrails_established"] = guardrails_established
    stats["global"]["solve_stage"] = solve_stage
    stats["global"]["preference_fairness_model"] = "V2558_VERTICAL_HORIZONTAL_HOLIDAY_COHORT_WATERFILL"
    stats["global"]["preference_vertical_order"] = ["ABSOLUTE_HARD","RESIDENT_HARD_ZERO_LOSS","CRITICAL_SPS_RO_SPS_UG_WEEKENDS_RAW_WATERFILL","CRITICAL_SPACING","WEEKLY_LOAD_RECOVERY_WATERFILL","HOLIDAY_CURRENT_MONTH_WATERFILL","STRUCTURAL_BURDEN","NONCRITICAL_POST_GUARDRAIL","SOFT1","SOFT2","SOFT3","CURRENT_MONTH_POST_OPTIMUM"]
    stats["global"]["holiday_waterfill_locks"] = dict(holiday_locks)
    stats["global"]["post_fairness_model"] = "V2577_ALL_POST_PLUS_FRIDAY_STRUCTURAL_WATERFILL"
    stats["global"]["weekly_load_waterfill"] = {
        "soft_target_hours":float(WEEKLY_LOAD_SOFT_TARGET_HOURS),
        "hard_rolling7_ceiling_hours":float(effective_max_hours7),
        "hard_max_workdays_rolling7":int(effective_max_workdays7),
        "worst_over40_lock":None if weekly_max_over40_lock is None else round(float(weekly_max_over40_lock),6),
        "total_over40_lock":None if weekly_total_over40_lock is None else round(float(weekly_total_over40_lock),6),
        "worst_calendar_week_spread_lock":None if weekly_worst_calendar_spread_lock is None else round(float(weekly_worst_calendar_spread_lock),6),
        "double_recovery_penalty_lock":None if weekly_recovery_penalty_lock is None else round(float(weekly_recovery_penalty_lock),6),
        "after_two_consecutive_doubles":"PM_ONLY_OR_OFF_HARD",
        "after_one_double":"NEXT_DAY_DOUBLE_DISCOURAGED",
        "monthly_double_spread_max":DOUBLE_SPREAD_MAX,
        "neutral_total_doubles_lock":neutral_total_doubles,
        "double_priority":"SPS_RO_SPS_UG_FIRST; SUNDAY_IS_SPS_RO; ONKO_FULL_9H_NOT_A_DOUBLE",
    }
    stats["global"]["post_system_hard_worst_spread_lock"] = int(post_system_worst_lock)
    stats["global"]["post_system_hard_total_spread_lock"] = int(post_system_total_lock)
    stats["global"]["post_system_hard_first_exposure_tiebreak"] = True
    stats["global"]["post_system_hard_per_post_spreads"] = dict(post_system_spreads)
    stats["global"]["post_system_hard_stage_optimal"] = bool(post_fill_res.x is not None and int(getattr(post_fill_res,"status",1))==0)
    stats["global"]["critical_structural_locked_spreads"] = dict(critical_spreads_locked)
    stats["global"]["critical_structural_worst_lock"] = int(critical_best_worst)
    stats["global"]["baseline_weekend_volunteer_mode"] = bool(baseline_weekend_volunteer_mode)
    stats["global"]["baseline_weekend_volunteers"] = [people[pi].initials for pi in active_weekend_volunteers]
    stats["global"]["baseline_weekend_volunteer_locks"] = dict(weekend_volunteer_locks)
    stats["global"]["weekend_volunteer_policy"] = (
        "SYSTEM_BASELINE_RAW_WATERFILL: weekend/SPS-RO exposure is water-filled on raw counts during generation; "
        "preferences do not bypass the corridor. Accepted ACTUAL swaps/overrides may later change the real distribution."
    )
    stats["global"]["critical_01_status"] = critical_01_trial_status
    stats["global"]["critical_corridor_search_log"] = list(critical_search_log)
    stats["global"]["critical_temporal_spacing_score_lock"] = critical_temporal_lock
    stats["global"]["noncritical_guardrail_ceiling"] = noncritical_guardrail_ceiling
    stats["global"]["noncritical_guardrail_status"] = noncritical_guardrail_status
    stats["global"]["noncritical_corridor_search_log"] = list(noncritical_search_log)
    stats["global"]["post_debt_enabled"] = False
    stats["global"]["future_fairness_catchup_enabled"] = False
    stats["global"]["fairness_history_role"] = "AUDIT_ONLY_NOT_SOLVER_INPUT"
    stats["global"]["soft_whitelist"] = [
        "Noriu laisvos (exact date/block)",
        "Pageidauju dirbti (exact date/block)",
        "Recurring weekend Pageidauju dirbti = SOFT only inside the raw SYSTEM water-fill corridor",
        "Vengti dublių / recovery",
        "Išsklaidymas-koncentracija"
    ]
    stats["global"]["deprecated_soft_ignored"] = [
        "generic weekday pattern",
        "recurring weekend Noriu laisvos",
        "station avoidance/seeking in free text"
    ]
    stats["global"]["holiday_days"] = sorted(public_holiday_days_in_month(year,month))
    stats["global"]["holiday_slot_count"] = len([s for s in slots if is_public_holiday(year,month,s.day) and not s.blocked])
    stats["global"]["holiday_preference_layer"] = "prefer-work first; neutral next; prefer-rest last; water-fill within current-month cohorts only; no historical catch-up"
    stats["global"]["soft_waterfill_locks"] = dict(waterfill_locks)
    stats["global"]["quality_repair_accepted_swaps"] = int(quality_repairs)
    stats["global"]["post_ceiling_rescue_attempted"] = bool(post_ceiling_rescue_attempted)
    stats["global"]["post_ceiling_rescue_succeeded"] = bool(post_ceiling_rescue_succeeded)
    try:
        stats["global"]["solver_worst_raw_post_spread"] = round(
            float(res.x[worst_raw_post_spread]),6
        )
    except Exception:
        stats["global"]["solver_worst_raw_post_spread"] = None
    try:
        stats["global"]["solver_worst_normalized_post_spread"] = round(
            float(res.x[worst_normalized_post_spread]),6
        )
    except Exception:
        stats["global"]["solver_worst_normalized_post_spread"] = None
    # Backward-compatible exact-preference diagnostic aliases. The primary V2.5.50
    # diagnostics are `soft_waterfill_locks` by vertical rank.
    stats["global"]["solver_min_exact_preference_ratio"] = None
    exact_active=set()
    for tier in ("SOFT1","SOFT2"):
        if tier in soft_tier_vars:
            exact_active.update(soft_tier_vars[tier]["active"])
    stats["global"]["solver_active_exact_preference_residents"] = int(len(exact_active))
    stats["global"]["solver_total_exact_preference_requests"] = int(sum(
        int(rec.get("count",0)) for tier in ("SOFT1","SOFT2")
        for rec in soft_tier_expr[tier].values()
    ))
    stats["global"]["resident_hard_total_requests"] = int(total_resident_hard_requests)
    stats["global"]["resident_hard_min_total_found"] = int(resident_hard_min_total)
    stats["global"]["resident_hard_minimum_proven"] = bool(rh_minimum_proven)
    stats["global"]["resident_hard_current_max_lock"] = int(resident_hard_current_max_lock)
    stats["global"]["resident_hard_cumulative_spread_lock"] = int(resident_hard_cumulative_spread_lock)
    stats["global"]["hard_classification"] = {
        "ABSOLUTE_HARD":"Generation and ACTUAL: safety/rest, justified absence, physical impossibility, coverage/overlap/qualification, exact monthly workload and even Onko pairing (0/2/4/...). Generation also applies <=48 known hours and <=6 workdays in every rolling 7 days. Post-publication bilateral voluntary NORMAL swaps may exceed only the 48h generation ceiling with explicit acknowledgement and may ACK consecutive Onko; exact workload and Onko parity remain non-relaxable.",
        "WEEKLY_RECOVERY":"Around-40h planning target is water-filled across residents; repeated doubles are de-clustered, and after two consecutive doubles the next day is PM-only or off.",
        "CRITICAL_STRUCTURAL":"SPS RO + SPS UG + weekends + Friday use raw current-month structural water-fill during SYSTEM generation. Preferences cannot widen the baseline corridor; only later ACTUAL swaps/overrides may change real exposure.",
        "RESIDENT_HARD":"`Negaliu dirbti` is mandatory during SYSTEM generation: zero violations are required and it is never traded against structural fairness or SOFT satisfaction. If mandatory availability cannot coexist with safety/coverage/exact workload, no SYSTEM draft is returned.",
        "NONCRITICAL_POST_CORE":"Every non-Onko ordinary post uses structural water-filling with target raw spread <=1 before SOFT. A wider <=2/<=3 corridor is allowed only after the tighter corridor is mathematically proven infeasible. No future-month post debt is created."
    }
    hard_ok = stats["global"]["hard_errors"] == 0
    critical_ok=bool(stats["global"].get("critical_spread_quality_gate_passed",False))
    noncritical_worst=int(stats["global"].get("noncritical_worst_spread",999) or 0)
    noncritical_ok=bool(noncritical_worst<=NONCRITICAL_SPREAD_LAST_RESORT_CEILING)
    pref_quality=stats["global"].get("preference_equity_quality_gate_passed")
    quality_issues=[]
    if not critical_ok:
        quality_issues.append(
            f"CRITICAL volunteer-adjusted SPS RO / SPS UG / weekend spread {stats['global'].get('critical_worst_spread')} > 1"
            if baseline_weekend_volunteer_mode else
            f"CRITICAL SPS RO / SPS UG / weekend spread {stats['global'].get('critical_worst_spread')} > 1"
        )
    if noncritical_worst>NONCRITICAL_SPREAD_LAST_RESORT_CEILING:
        quality_issues.append(
            f"ordinary post spread {noncritical_worst} > last-resort ceiling {NONCRITICAL_SPREAD_LAST_RESORT_CEILING}"
        )
    elif noncritical_worst>NONCRITICAL_SPREAD_NORMAL_CEILING:
        quality_issues.append(
            f"ordinary post spread {noncritical_worst}: 0-1 water-fill was proven infeasible; wider certified corridor used"
        )
    if pref_quality is False:
        quality_issues.append(
            f"active SOFT fulfilment spread {stats['global'].get('soft_preference_score_spread')} pp > 15 pp target"
        )
    if not bool(stats["global"].get("weekly_load_safety_gate_passed",True)):
        quality_issues.append("weekly load / recovery safety gate failed")
    stats["global"]["generation_quality_issues"]=quality_issues
    weekly_ok=bool(stats["global"].get("weekly_load_safety_gate_passed",True))
    stats["global"]["generation_quality_gate_passed"]=bool(critical_ok and noncritical_ok and weekly_ok)
    ok = bool(hard_ok and critical_ok and noncritical_ok and weekly_ok)

    if not hard_ok:
        final_message = "VALIDATION — FAILED"
    elif not critical_ok:
        final_message = (
            "HARD VALIDATION — PASSED, BUT CRITICAL STRUCTURAL GATE — FAILED. "
            "Volunteer-adjusted SPS RO / SPS UG / remaining weekend burden must stay at max-min 0-1; this draft is rejected."
            if baseline_weekend_volunteer_mode else
            "HARD VALIDATION — PASSED, BUT CRITICAL STRUCTURAL GATE — FAILED. "
            "SPS RO, SPS UG and weekend exposure must stay at max-min 0-1 whenever feasible; this draft is rejected."
        )
    elif not noncritical_ok:
        final_message = (
            "HARD/CRITICAL VALIDATION — PASSED, BUT NONCRITICAL POST GATE — FAILED. "
            f"Worst ordinary post spread is {noncritical_worst}; even the last-resort ceiling is {NONCRITICAL_SPREAD_LAST_RESORT_CEILING}."
        )
    elif noncritical_worst>NONCRITICAL_SPREAD_NORMAL_CEILING:
        final_message = (
            "VALIDATION — PASSED — CRITICAL SPS/WEEKEND 0-1 PROTECTED; "
            "A WIDER ORDINARY-POST WATER-FILL CORRIDOR WAS USED ONLY AFTER 0-1 WAS PROVEN INFEASIBLE; POST DEBT RECORDED."
        )
    else:
        final_message = (
            "VALIDATION — PASSED — BASELINE WEEKEND VOLUNTEERS HONORED WHERE FEASIBLE; REMAINING NON-VOLUNTARY WEEKEND/SPS-RO + SPS-UG FAIRNESS 0-1 PROTECTED; RAW VOLUNTEER EXPOSURE SAVED FOR FUTURE BALANCING; "
            "WEEKLY LOAD/RECOVERY WATER-FILL ACTIVE; ORDINARY POSTS STRUCTURALLY WATER-FILLED."
            if baseline_weekend_volunteer_mode else
            "VALIDATION — PASSED — CRITICAL SPS/WEEKEND 0-1 PROTECTED; "
            "WEEKLY LOAD/RECOVERY WATER-FILL ACTIVE (40h target, <=48h rolling-7 GENERATION ceiling; voluntary normal-swap >48h only with explicit ACK); "
            "ORDINARY POSTS STRUCTURALLY WATER-FILLED TOWARD <=1 BEFORE SOFT; LONGITUDINAL POST-DEBT OPTIMIZATION APPLIED."
        )

    return SolveResult(
        ok=ok,
        message=final_message,
        assignments=assignments,
        targets=targets,
        stats=stats,
        objective_value=float(res.fun) if getattr(res, "fun", None) is not None else None,
        request_snapshot=request_snapshot,
    )


def _directional_score(metric: float, center: float, preference: int, step: float) -> Optional[float]:
    if preference == 0:
        return None
    desired = center + step * preference
    distance = abs(metric - desired)
    return max(0.0, min(100.0, 100.0 - 28.0 * distance))


def validate_schedule(year: int, month: int, people: List[Person], slots: List[Slot],
                      assignments: Dict[int, str], targets: Dict[str, int],
                      satisfaction_people: Optional[List[Person]] = None,
                      backup_assignments: Optional[List[dict]] = None,
                      weekly_hours_override_caps: Optional[Dict[str, float]] = None,
                      validation_mode: str = "generation") -> Dict[str, dict]:
    errors: List[str] = []
    structural_warnings: List[str] = []
    # V2.5.115: theoretical backup/standby validation is a separate layer.
    # It must never turn a valid NORMAL schedule or a resident preference into a miss.
    backup_layer_errors: List[str] = []
    validation_mode=str(validation_mode or "generation")
    post_publication_mode=(
        validation_mode.startswith("voluntary_swap")
        or validation_mode in {"emergency_rescue","backup_swap_actual","actual_operational"}
    )
    voluntary_swap_mode=post_publication_mode
    weekly_hours_override_caps={str(k):float(v) for k,v in (weekly_hours_override_caps or {}).items()}
    _, ndays = calendar.monthrange(year, month)

    _validation_weekend_slots=[s for s in slots if s.weekday>=5]
    # V2.5.104: explicit weekend positive requests are voluntary burden choices.
    # SYSTEM fairness validates the remaining non-voluntary load; raw exposure is
    # still reported separately and ACTUAL swaps may widen it further.
    _baseline_weekend_volunteer_mode=any(
        any(date(year,month,int(d)).weekday()>=5 for d in (set(p.preferred)|set(p.preferred_am)|set(p.preferred_pm)))
        for p in people
    )

    pdata = {
        p.initials: {
            "name": p.name,
            "target": targets[p.initials],
            "workload": 0.0,
            "assignments": 0,
            "weekday_assignments": 0,
            "weekday_days": 0,
            "weekend_assignments": 0,
            "holiday_assignments": 0,
            "holiday_preference": int(getattr(p,"holiday_preference",0) or 0),
            "prior_holiday_count": int(getattr(p,"prior_holiday_count",0) or 0),
            "cumulative_holiday_count": int(getattr(p,"prior_holiday_count",0) or 0),
            "voluntary_weekend_assignments": 0,
            "voluntary_weekend_sps_ro_assignments": 0,
            "fairness_weekend_assignments": 0,
            "fairness_sps_ro_assignments": 0,
            "prior_weekend_count": p.prior_weekend_count,
            "cumulative_weekend_count": p.prior_weekend_count,
            "cumulative_fair_weekend_count": p.prior_weekend_count,
            "prior_friday_count": p.prior_friday_count,
            "cumulative_friday_count": p.prior_friday_count,
            "prior_double_count": p.prior_double_count,
            "cumulative_double_count": p.prior_double_count,
            "prior_weekday_day_count": p.prior_weekday_day_count,
            "cumulative_weekday_day_count": p.prior_weekday_day_count,
            "friday_assignments": 0,
            "voluntary_friday_assignments": 0,
            "fairness_friday_assignments": 0,
            "doubles": 0,
            "saturdays": 0,
            "sundays": 0,
            "voluntary_saturdays": 0,
            "voluntary_sundays": 0,
            "fairness_saturdays": 0,
            "fairness_sundays": 0,
            "preferred_days_requested": len(p.preferred) + len(p.preferred_am) + len(p.preferred_pm),
            "preferred_days_worked": 0,
            "soft_free_requested": len(p.soft_free) + len(p.soft_free_am) + len(p.soft_free_pm),
            "soft_free_honored": 0,
            "exact_preference_requests": (
                len(p.preferred) + len(p.preferred_am) + len(p.preferred_pm)
                + len(p.soft_free) + len(p.soft_free_am) + len(p.soft_free_pm)
            ),
            "directional_preference_requests": sum([
                1 if p.spread_preference != 0 else 0,
                1 if p.avoid_doubles else 0,
            ]),
            "prior_consecutive_weekend_streak": int(getattr(p,"prior_consecutive_weekend_streak",0) or 0),
            "prior_last_day_onko": bool(getattr(p,"prior_last_day_onko",False)),
            "consecutive_onko_pairs": [],
            "max_consecutive_weekends": 0,
            "max_consecutive_days": 0,
            "max_rolling7_hours": 0.0,
            "max_calendar_week_hours": 0.0,
            "weekly_hours": {},
            "fully_free_days": 0,
            "consecutive_double_pairs": 0,
            "worked_after_two_doubles": 0,
            "weekly48_override_windows": [],
            "rolling7_windows": [],
            "double_days": [],
            "six_day_streak": False,
            "distinct_work_days": 0,
            "dispersion_index": 0.0,
            "rotation_counts": {cat:0 for cat in ROTATION_CATEGORIES},
            "prior_rotation_counts": {cat:int(p.prior_rotation_counts.get(cat,0)) for cat in ROTATION_CATEGORIES},
            "cumulative_rotation_counts": {cat:int(p.prior_rotation_counts.get(cat,0)) for cat in ROTATION_CATEGORIES},
            "distinct_rotations": 0,
            "preference_score": None,
            "preference_components": {},
        }
        for p in people
    }

    # Coverage.
    onko_slots = [s for s in slots if s.department == "Onko RO centre" and not s.blocked]
    onko_filled = sum(1 for s in onko_slots if s.idx in assignments)
    expected_onko = len(onko_slots) if len(onko_slots) % 2 == 0 else len(onko_slots) - 1
    if onko_filled != expected_onko:
        errors.append(f"Onko coverage {onko_filled} != {expected_onko}")

    for s in slots:
        assigned = s.idx in assignments
        if s.blocked and assigned:
            errors.append(f"Blocked slot filled: {s.day} {s.department} {s.block}")
        if s.mandatory and s.department != "Onko RO centre" and not assigned:
            errors.append(f"Mandatory slot unfilled: {s.day} {s.department} {s.block}")

    # Optional-gap distribution validation / diagnostics.
    optional_gap_rows=[]
    for d in range(1,ndays+1):
        day_gaps=[
            s for s in slots
            if s.day==d and not s.blocked and not s.mandatory
            and s.department!="Onko RO centre"
            and s.idx not in assignments
        ]
        onko_day_gaps=[
            s for s in slots
            if s.day==d and s.department=="Onko RO centre" and s.idx not in assignments
        ]
        all_day_gaps=day_gaps+onko_day_gaps
        for s in all_day_gaps:
            optional_gap_rows.append({
                "day":s.day,"department":s.department,"block":s.block,
                "rotation":rotation_category(s),
            })

    # V2.5.40 gap-distribution validation.
    actual_optional=[r for r in optional_gap_rows if r["department"]!="Onko RO centre"]
    cat_gap_counts={}
    for r in actual_optional:
        cat_gap_counts[r["rotation"]]=cat_gap_counts.get(r["rotation"],0)+1

    optional_categories=sorted({
        rotation_category(s) for s in slots
        if not s.blocked and not s.mandatory and s.department!="Onko RO centre"
        and rotation_category(s)!="Mamografijos"
    })
    cat_vals=[cat_gap_counts.get(cat,0) for cat in optional_categories]
    optional_gap_category_spread=(max(cat_vals)-min(cat_vals)) if cat_vals else 0

    # V2.5.81: optional-gap pattern/distribution is a SYSTEM-generation structural
    # rule only. ACTUAL voluntary swaps, backup changes and operational rescues may
    # create/worsen optional gaps or spread without being blocked. The published
    # SYSTEM fairness/gap baseline remains frozen for audit.
    if (not voluntary_swap_mode) and optional_gap_category_spread>2:
        errors.append(
            f"Gap workplace dispersion violated: category spread {optional_gap_category_spread} > 2"
        )

    _fixed_expected,_gap_meta,_gap_plan_errors=plan_distributed_gaps(
        year,month,people,slots,targets
    )
    expected_gap_days=sorted(_gap_meta.get("gap_days",[])) if not _gap_plan_errors else []
    actual_gap_days=sorted({r["day"] for r in optional_gap_rows})
    if (not voluntary_swap_mode) and (not _gap_plan_errors) and actual_gap_days!=expected_gap_days:
        errors.append(
            f"Gap-day dispersion pattern outdated: actual {actual_gap_days}, expected {expected_gap_days}"
        )
    if (not voluntary_swap_mode) and (not _gap_plan_errors):
        expected_counts={int(d):int(c) for d,c in (_gap_meta.get("optional_gap_counts") or {}).items()}
        onko_day=_gap_meta.get("onko_gap_day")
        if onko_day:
            expected_counts[int(onko_day)]=expected_counts.get(int(onko_day),0)+1
        actual_counts={}
        for r in optional_gap_rows:
            actual_counts[int(r["day"])]=actual_counts.get(int(r["day"]),0)+1
        expected_counts={d:c for d,c in expected_counts.items() if c>0}
        if actual_counts!=expected_counts:
            errors.append(f"Gap counts do not match the planned distribution: actual {actual_counts}, expected {expected_counts}")

    # Per person.
    for p in people:
        pslots = [s for s in slots if assignments.get(s.idx) == p.initials]
        d = pdata[p.initials]
        d["assignments"] = len(pslots)
        d["workload"] = sum(s.workload2 for s in pslots) / 2.0
        d["weekday_assignments"] = sum(s.weekday < 5 for s in pslots)
        d["weekend_assignments"] = sum(s.weekday >= 5 for s in pslots)
        d["holiday_assignments"] = sum(is_public_holiday(year,month,s.day) for s in pslots)
        d["cumulative_holiday_count"] = int(getattr(p,"prior_holiday_count",0) or 0) + d["holiday_assignments"]
        d["friday_assignments"] = sum(s.weekday == 4 for s in pslots)
        # Request-semantic volunteer units:
        # - whole-day weekend "prefer to work" = max ONE voluntary unit that day;
        # - AM and PM requests can each be one unit when explicitly requested.
        # This prevents a whole-day request from being interpreted as "give me both
        # AM and PM" while still allowing a 12h day if the schedule independently
        # needs the second half.
        _vol_weekend=0
        _vol_weekend_sps=0
        _vol_sat=0
        _vol_sun=0
        _weekend_days=sorted({s.day for s in pslots if s.weekday>=5})
        for _d in _weekend_days:
            _day_slots=[s for s in pslots if s.day==_d and s.weekday>=5]
            if _d in p.preferred:
                if _day_slots:
                    _vol_weekend+=1
                    if date(year,month,_d).weekday()==5: _vol_sat+=1
                    elif date(year,month,_d).weekday()==6: _vol_sun+=1
                    if any(rotation_category(s)=="SPS RO" for s in _day_slots):
                        _vol_weekend_sps+=1
            else:
                if _d in p.preferred_am:
                    _hits=[s for s in _day_slots if blocks_overlap(s.block,"AM")]
                    if _hits:
                        _vol_weekend+=1
                        if date(year,month,_d).weekday()==5: _vol_sat+=1
                        elif date(year,month,_d).weekday()==6: _vol_sun+=1
                        if any(rotation_category(s)=="SPS RO" for s in _hits):
                            _vol_weekend_sps+=1
                if _d in p.preferred_pm:
                    _hits=[s for s in _day_slots if blocks_overlap(s.block,"PM")]
                    if _hits:
                        _vol_weekend+=1
                        if date(year,month,_d).weekday()==5: _vol_sat+=1
                        elif date(year,month,_d).weekday()==6: _vol_sun+=1
                        if any(rotation_category(s)=="SPS RO" for s in _hits):
                            _vol_weekend_sps+=1
        d["voluntary_weekend_assignments"] = int(_vol_weekend)
        d["voluntary_weekend_sps_ro_assignments"] = int(_vol_weekend_sps)
        d["voluntary_friday_assignments"] = sum(s.weekday == 4 and preferred_for_slot(p, s.day, s.block) for s in pslots)
        # V2.5.104: explicit weekend-work volunteers are removed from the CURRENT
        # fairness burden in every month. Raw fatigue/exposure remains visible;
        # prior-month history is audit-only and never creates future catch-up.
        d["fairness_weekend_assignments"] = (
            d["weekend_assignments"]-d["voluntary_weekend_assignments"]
            if _baseline_weekend_volunteer_mode else d["weekend_assignments"]
        )
        d["cumulative_fair_weekend_count"] = (
            int(p.prior_weekend_count)+int(d["fairness_weekend_assignments"])
        )
        d["fairness_friday_assignments"] = d["friday_assignments"]  # Friday rule unchanged
        d["saturdays"] = sum(s.weekday == 5 for s in pslots)
        d["sundays"] = sum(s.weekday == 6 for s in pslots)
        d["voluntary_saturdays"] = int(_vol_sat)
        d["voluntary_sundays"] = int(_vol_sun)
        d["fairness_saturdays"] = (d["saturdays"]-d["voluntary_saturdays"] if _baseline_weekend_volunteer_mode else d["saturdays"])
        d["fairness_sundays"] = (d["sundays"]-d["voluntary_sundays"] if _baseline_weekend_volunteer_mode else d["sundays"])

        # Workplace / modality exposure ledger.
        for cat in ROTATION_CATEGORIES:
            n=sum(1 for s in pslots if rotation_category(s)==cat)
            d["rotation_counts"][cat]=n
            d["cumulative_rotation_counts"][cat]=int(p.prior_rotation_counts.get(cat,0))+n
        d["fairness_sps_ro_assignments"]=(
            int(d["rotation_counts"].get("SPS RO",0))
            - int(d["voluntary_weekend_sps_ro_assignments"])
            if _baseline_weekend_volunteer_mode
            else int(d["rotation_counts"].get("SPS RO",0))
        )
        d["distinct_rotations"]=sum(1 for n in d["rotation_counts"].values() if n>0)

        # Cumulative critical weekend exposure includes ALL worked weekend shifts.
        d["cumulative_weekend_count"] = p.prior_weekend_count + d["weekend_assignments"]
        d["cumulative_friday_count"] = p.prior_friday_count + d["fairness_friday_assignments"]

        # Temporal weekend clustering, including the preceding-month tail streak.
        weekend_anchors=sorted({(sl.day if sl.weekday==5 else sl.day-1) for sl in pslots if sl.weekday>=5})
        all_month_anchors=sorted({(sl.day if sl.weekday==5 else sl.day-1) for sl in slots if sl.weekday>=5})
        worked_flags=[1 if a in set(weekend_anchors) else 0 for a in all_month_anchors]
        prior_streak=max(0,int(getattr(p,"prior_consecutive_weekend_streak",0) or 0))
        cur=prior_streak; best=prior_streak
        for flag in worked_flags:
            if flag:
                cur+=1; best=max(best,cur)
            else:
                cur=0
        d["max_consecutive_weekends"]=int(best)

        actual_assignment_workload=float(d["workload"])
        d["actual_assignment_workload"]=round(actual_assignment_workload,1)
        if post_publication_mode:
            # V2.5.85 constitution: publication freezes monthly workload CREDIT.
            # ACTUAL swaps, backup swaps and Emergency Rescue only change placement.
            # They never add/subtract/transfer target units and never create a work debt.
            d["workload_credit"]=float(targets[p.initials])
            d["workload_target_delta"]=0.0
            d["workload_credit_policy"]="FROZEN_SYSTEM_LEDGER"
        else:
            workload_delta=actual_assignment_workload-float(targets[p.initials])
            d["workload_credit"]=actual_assignment_workload
            d["workload_target_delta"]=round(workload_delta,1)
            d["workload_credit_policy"]="SYSTEM_GENERATION_EXACT"
            if abs(workload_delta) > 1e-9:
                errors.append(f"{p.initials}: workload {d['workload']} must equal exact target {targets[p.initials]}")

        onko_n = sum(s.department == "Onko RO centre" for s in pslots)
        if onko_n % 2 != 0:
            errors.append(f"{p.initials}: odd Onko count {onko_n} is forbidden; Onko must be assigned in even pairs (0, 2, 4, ...)")

        onko_days=sorted({s.day for s in pslots if s.department=="Onko RO centre"})
        consecutive_onko=[]
        if bool(getattr(p,"prior_last_day_onko",False)) and 1 in onko_days:
            consecutive_onko.append([0,1])
        consecutive_onko += [[a,b] for a,b in zip(onko_days,onko_days[1:]) if b==a+1]
        d["consecutive_onko_pairs"]=consecutive_onko
        if consecutive_onko and (not voluntary_swap_mode):
            # V2.5.69: consecutive Onko RO remains a HARD generation rule so the
            # algorithm itself never creates back-to-back 9 h Onko days. A later
            # bilateral voluntary swap may override this generator rule with an
            # explicit consequence acknowledgement; true ABSOLUTE legal/physical
            # blockers (rest, overlap, justified absence, etc.) still remain blocks.
            pretty=", ".join(f"{a or 'prev'}→{b}" for a,b in consecutive_onko)
            errors.append(f"{p.initials}: consecutive Onko RO days are forbidden in SYSTEM generation ({pretty})")

        worked_days: Set[int] = set()
        weekday_days: Set[int] = set()

        for day in range(1, ndays + 1):
            ds = [s for s in pslots if s.day == day]
            if not ds:
                continue
            worked_days.add(day)
            if date(year, month, day).weekday() < 5:
                weekday_days.add(day)

            for s in ds:
                if absolute_assignment_blocked(p, day, s.block):
                    errors.append(
                        f"{p.initials}: assigned during ABSOLUTE-HARD unavailable time "
                        f"on day {day} ({s.block})"
                    )
                if (not post_publication_mode) and resident_hard_unavailable_for_block(p, day, s.block):
                    errors.append(
                        f"{p.initials}: assigned during mandatory RESIDENT-HARD `Negaliu dirbti` "
                        f"on day {day} ({s.block})"
                    )
            if len(ds) > int(rule_value("max_assignments_per_day")):
                errors.append(f"{p.initials}: assignments/day cap exceeded on day {day}")

            am = sum(s.block in ("AM", "FULL") for s in ds)
            pm = sum(s.block in ("PM", "FULL") for s in ds)
            if am > 1 or pm > 1:
                errors.append(f"{p.initials}: overlapping assignments on day {day}")
            if len(ds) == 2:
                d["doubles"] += 1

        d["distinct_work_days"] = len(worked_days)
        d["weekday_days"] = len(weekday_days)
        d["cumulative_double_count"] = p.prior_double_count + d["doubles"]
        d["cumulative_weekday_day_count"] = p.prior_weekday_day_count + d["weekday_days"]
        # Count SOFT requests as explicit request units: whole day, AM and PM.
        # A FULL assignment satisfies both an AM and a PM work request and violates
        # either corresponding free-time request because it overlaps both blocks.
        preferred_satisfied = sum(1 for day in p.preferred if day in worked_days)
        preferred_satisfied += sum(1 for day in p.preferred_am if any(s.day == day and blocks_overlap(s.block, "AM") for s in pslots))
        preferred_satisfied += sum(1 for day in p.preferred_pm if any(s.day == day and blocks_overlap(s.block, "PM") for s in pslots))
        soft_honored = sum(1 for day in p.soft_free if day not in worked_days)
        soft_honored += sum(1 for day in p.soft_free_am if not any(s.day == day and blocks_overlap(s.block, "AM") for s in pslots))
        soft_honored += sum(1 for day in p.soft_free_pm if not any(s.day == day and blocks_overlap(s.block, "PM") for s in pslots))
        d["preferred_days_worked"] = preferred_satisfied
        d["soft_free_honored"] = soft_honored
        d["dispersion_index"] = (
            len(worked_days) / max(1, len(pslots))
            if pslots else 0.0
        )

        cur = best = 0
        for day in range(1, ndays + 1):
            if day in worked_days:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        d["max_consecutive_days"] = best
        d["fully_free_days"] = int(ndays-len(worked_days))

        # V2.5.53 temporal workload diagnostics. Calendar-week hours are shown
        # explicitly so a resident cannot silently receive a 60h first week.
        def _vh(s):
            return 9.0 if s.block == "FULL" else 6.0
        week_hours={}
        for sl in pslots:
            dt=date(year,month,sl.day)
            wk=f"{dt.isocalendar().year}-W{int(dt.isocalendar().week):02d}"
            week_hours[wk]=week_hours.get(wk,0.0)+_vh(sl)
        d["weekly_hours"]={k:round(v,1) for k,v in sorted(week_hours.items())}
        d["max_calendar_week_hours"]=round(max(list(week_hours.values())+[0.0]),1)

        double_days=set()
        for day in range(1,ndays+1):
            if len([sl for sl in pslots if sl.day==day])==2:
                double_days.add(day)
        d["double_days"]=sorted(int(x) for x in double_days)
        d["consecutive_double_pairs"]=sum(1 for day in double_days if day+1 in double_days)
        post_two=0
        for day in range(3,ndays+1):
            if (day-2 in double_days) and (day-1 in double_days):
                today=[sl for sl in pslots if sl.day==day]
                if today:
                    post_two+=1
                # V2.5.55: this remains a generator/recovery shaping HARD rule, but
                # a voluntary bilateral swap may knowingly accept the fatigue pattern.
                if (not voluntary_swap_mode) and any(blocks_overlap(sl.block,"AM") for sl in today):
                    errors.append(
                        f"{p.initials}: after two consecutive double days, day {day} must be PM-only or free"
                    )
        d["worked_after_two_doubles"]=int(post_two)

        # Safety validation for work known to this scheduler.

        for day in range(1, ndays + 1):
            h = sum(_vh(s) for s in pslots if s.day == day)
            daily_cap=(float(SWAP_MAX_HOURS_PER_DAY) if voluntary_swap_mode else float(rule_value("max_hours_per_day")))
            if h > daily_cap + 1e-4:
                errors.append(f"{p.initials}: {h:g}h on day {day} exceeds max hours/day")

        rolling7_values=[]
        # Generation: strict 48h/7d fatigue/scheduling ceiling. Voluntary swap:
        # preserve the user's requested real-world flexibility, but never exceed
        # the 60h absolute envelope or 6 working days in any rolling 7.
        effective_days7=(
            int(SWAP_MAX_WORKDAYS_ROLLING7) if voluntary_swap_mode
            else min(int(rule_value("max_workdays_rolling7")),int(FATIGUE_MAX_WORKDAYS_ROLLING7))
        )
        effective_hours7=(
            min(float(rule_value("swap_max_hours_rolling7")),float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7)) if voluntary_swap_mode
            else min(float(rule_value("max_hours_rolling7")),float(FATIGUE_ROLLING7_HARD_CEILING_HOURS))
        )
        for start_d in range(1, ndays - 6 + 1):
            end_d = start_d + 6
            worked7 = {s.day for s in pslots if start_d <= s.day <= end_d}
            if len(worked7) > effective_days7:
                errors.append(f"{p.initials}: workdays/7d cap exceeded in {start_d}-{end_d}")
            h7 = sum(_vh(s) for s in pslots if start_d <= s.day <= end_d)
            rolling7_values.append(float(h7))
            d["rolling7_windows"].append({
                "start_day":int(start_d),"end_day":int(end_d),"hours":round(float(h7),1),
                "workdays":int(len(worked7)),
            })
            if h7 > effective_hours7 + 1e-4:
                accepted_cap=float(weekly_hours_override_caps.get(p.initials, effective_hours7))
                if (not voluntary_swap_mode) and h7 <= accepted_cap + 1e-4:
                    d["weekly48_override_windows"].append({
                        "start_day":int(start_d),"end_day":int(end_d),
                        "hours":round(float(h7),1),"baseline_ceiling":round(float(effective_hours7),1),
                        "accepted_cap":round(float(accepted_cap),1),
                    })
                else:
                    errors.append(f"{p.initials}: hours/7d cap exceeded in {start_d}-{end_d} ({h7:g}h > {effective_hours7:g}h)")
        d["max_rolling7_hours"]=round(max(rolling7_values+[0.0]),1)
        d["six_day_streak"]=bool(int(d.get("max_consecutive_days",0) or 0) >= 6)

        start_hour = {"AM": 8, "FULL": 8, "PM": 14}
        end_hour = {"AM": 14, "FULL": 17, "PM": 20}
        for a in pslots:
            for b in pslots:
                if b.day == a.day + 1:
                    rest = (24 - end_hour[a.block]) + start_hour[b.block]
                    min_rest=(float(SWAP_MIN_DAILY_REST_HOURS) if voluntary_swap_mode else float(rule_value("min_rest_hours")))
                    if rest < min_rest:
                        errors.append(f"{p.initials}: only {rest}h rest between days {a.day}-{b.day}")

        for duty_day in p.long_duty:
            next_day = duty_day + 1
            if 1 <= next_day <= ndays and any(s.day == next_day for s in pslots):
                errors.append(f"{p.initials}: work on mandatory post-duty rest day {next_day}")

        for vac_day in p.vacation:
            if any(s.day == vac_day for s in pslots):
                errors.append(f"{p.initials}: work during vacation day {vac_day}")
        for abs_day in p.justified_absence:
            if any(s.day == abs_day for s in pslots):
                errors.append(f"{p.initials}: work during justified absence day {abs_day}")

    # V2.5.32 backup-availability validation: WEEKEND + SPS RO + SPS UG.
    for covered in slots:
        if not backup_required_slot(covered):
            continue
        covered_person = assignments.get(covered.idx)
        if not covered_person:
            continue
        eligible = []
        for p in people:
            if p.initials == covered_person:
                continue
            if absolute_unavailable_for_block(p, covered.day, covered.block):
                continue
            if (not post_publication_mode) and resident_hard_unavailable_for_block(p, covered.day, covered.block):
                continue
            pslots = [
                s for s in slots
                if s.day == covered.day and assignments.get(s.idx) == p.initials
            ]
            if any(blocks_overlap(s.block, covered.block) for s in pslots):
                continue
            eligible.append(p.initials)
        if not eligible:
            errors.append(
                f"Day {covered.day} {covered.department} {covered.block}: "
                f"no HARD-available non-overlapping backup resident"
            )

    # Weekend uniqueness validation from active Rule Profile.
    if (not voluntary_swap_mode) and bool(rule_value("weekend_unique_required")):
        saturdays = [d for d in range(1, ndays + 1) if date(year, month, d).weekday() == 5]
        for sat in saturdays:
            sun = sat + 1
            if sun <= ndays and date(year, month, sun).weekday() == 6:
                ws = [s for s in slots if s.day in (sat, sun)]
                assigned_people = [assignments.get(s.idx) for s in ws if assignments.get(s.idx)]
                cap=int(rule_value("weekend_max_assignments_per_resident"))
                counts={i:assigned_people.count(i) for i in set(assigned_people)}
                if any(v>cap for v in counts.values()):
                    structural_warnings.append(f"Weekend {sat}-{sun}: resident weekend-pair target exceeded")

    # V2.5.115 THEORETICAL BACKUP LAYER.
    # Planned or activated-only backup duties are STANDBY, not work. They have zero
    # effect on SYSTEM/DRAFT workload, rest, water-fill or request satisfaction.
    # Only a row marked COMPLETED represents real-life cover and may affect ACTUAL
    # request realization; real-work fairness ownership is handled separately by
    # effective_actual_assignments().
    slot_by_idx={s.idx:s for s in slots}
    backup_rows=[]
    for raw in (backup_assignments or []):
        try:
            sid=int(raw.get("covered_slot"))
        except Exception:
            continue
        sl=slot_by_idx.get(sid)
        if sl is None:
            continue
        backup=str(raw.get("actual_backup") or raw.get("planned_backup") or raw.get("backup") or "")
        if not backup:
            continue
        backup_rows.append({
            "covered_slot":sid,
            "backup":backup,
            "covered_person":str(raw.get("covered_person") or assignments.get(sid) or ""),
            "day":sl.day,"block":sl.block,"department":sl.department,
            "activated_at":raw.get("activated_at"),
            "completed_at":raw.get("completed_at"),
        })

    # Backup obligations may never violate ABSOLUTE HARD or overlap the same
    # resident's normal assignment. RESIDENT HARD is deliberately not an error:
    # it is recorded as a high-priority request loss below.
    for br in backup_rows:
        bp=next((p for p in people if p.initials==br["backup"]),None)
        if bp is None:
            backup_layer_errors.append(f"Backup slot {br['covered_slot']}: unknown backup resident {br['backup']}")
            continue
        if br["backup"]==br["covered_person"]:
            backup_layer_errors.append(f"Backup slot {br['covered_slot']}: resident cannot back up own assignment")
        if absolute_unavailable_for_block(bp,br["day"],br["block"]):
            backup_layer_errors.append(f"{br['backup']}: backup during ABSOLUTE HARD on day {br['day']} {br['block']}")
        if (not post_publication_mode) and resident_hard_unavailable_for_block(bp,br["day"],br["block"]):
            backup_layer_errors.append(f"{br['backup']}: backup during mandatory RESIDENT HARD on day {br['day']} {br['block']}")
        normal_here=[sl for sl in slots if sl.day==br["day"] and assignments.get(sl.idx)==br["backup"]]
        if any(blocks_overlap(sl.block,br["block"]) for sl in normal_here):
            backup_layer_errors.append(f"{br['backup']}: backup overlaps normal assignment on day {br['day']} {br['block']}")

    # V2.5.49 RESIDENT REQUEST SATISFACTION LEDGER.
    # Every structured resident-facing table is represented, but pure legal/physical
    # ABSOLUTE HARD facts are audited separately so guaranteed safety rows cannot
    # artificially inflate a resident's preference percentage.
    weekend_avg = np.mean([v["weekend_assignments"] for v in pdata.values()]) if pdata else 0
    weekday_day_avg = np.mean([v["weekday_days"] for v in pdata.values()]) if pdata else 0

    satisfaction_map={q.initials:q for q in (satisfaction_people or people)}
    _sat_people=list(satisfaction_map.values())
    _double_counts={i:int((pdata.get(i) or {}).get("doubles",0) or 0) for i in pdata}
    _group_double_min=min(_double_counts.values()) if _double_counts else 0
    _group_double_max=max(_double_counts.values()) if _double_counts else 0
    _weekend_counts={i:int((pdata.get(i) or {}).get("weekend_assignments",0) or 0) for i in pdata}
    _group_weekend_min=min(_weekend_counts.values()) if _weekend_counts else 0
    _group_weekend_max=max(_weekend_counts.values()) if _weekend_counts else 0
    _weekday_days_counts={i:int((pdata.get(i) or {}).get("weekday_days",0) or 0) for i in pdata}
    _group_weekday_min=min(_weekday_days_counts.values()) if _weekday_days_counts else 0
    _group_weekday_max=max(_weekday_days_counts.values()) if _weekday_days_counts else 0
    _pref12_names=[
        q.initials for q in _sat_people
        if max(0,min(3,int(getattr(q,"shift_length_preference",0) or 0)))==3
    ]
    _pref6_names=[
        q.initials for q in _sat_people
        if max(0,min(3,int(getattr(q,"shift_length_preference",0) or 0)))==1
        or (
            max(0,min(3,int(getattr(q,"shift_length_preference",0) or 0)))==0
            and bool(getattr(q,"avoid_doubles",False))
        )
    ]
    for p in people:
        sp=satisfaction_map.get(p.initials,p)
        d = pdata[p.initials]
        pslots=[s for s in slots if assignments.get(s.idx)==p.initials]
        worked_days={s.day for s in pslots}
        components={}
        preferred_satisfied = sum(1 for day in sp.preferred if day in worked_days)
        preferred_satisfied += sum(1 for day in sp.preferred_am if any(sl.day == day and blocks_overlap(sl.block, "AM") for sl in pslots))
        preferred_satisfied += sum(1 for day in sp.preferred_pm if any(sl.day == day and blocks_overlap(sl.block, "PM") for sl in pslots))
        soft_honored = sum(1 for day in sp.soft_free if day not in worked_days)
        soft_honored += sum(1 for day in sp.soft_free_am if not any(sl.day == day and blocks_overlap(sl.block, "AM") for sl in pslots))
        soft_honored += sum(1 for day in sp.soft_free_pm if not any(sl.day == day and blocks_overlap(sl.block, "PM") for sl in pslots))
        d["preferred_days_worked"]=int(preferred_satisfied)
        d["soft_free_honored"]=int(soft_honored)

        # Keep the old exact-SOFT fields for backward compatibility/research, while
        # the PRIMARY `preference_score` below becomes the complete resident-request
        # satisfaction score.
        preferred_requested = len(sp.preferred) + len(sp.preferred_am) + len(sp.preferred_pm)
        if preferred_requested:
            components["preferred_dates"] = round(
                100.0 * d["preferred_days_worked"] / preferred_requested, 1
            )
        soft_requested = len(sp.soft_free) + len(sp.soft_free_am) + len(sp.soft_free_pm)
        if soft_requested:
            components["soft_free_days"] = round(
                100.0 * d["soft_free_honored"] / soft_requested, 1
            )
        exact_requested=preferred_requested+soft_requested
        exact_honored=preferred_satisfied+soft_honored
        d["exact_preference_honored"]=int(exact_honored)
        d["exact_preference_score"]=(
            round(100.0*exact_honored/exact_requested,1)
            if exact_requested else None
        )

        if sp.weekday_preference != 0:
            cur=int(d.get("weekday_days",0) or 0)
            if _group_weekday_max==_group_weekday_min:
                score=100.0
            elif sp.weekday_preference>0:
                score=100.0*(cur-_group_weekday_min)/max(1,_group_weekday_max-_group_weekday_min)
            else:
                score=100.0*(_group_weekday_max-cur)/max(1,_group_weekday_max-_group_weekday_min)
            components["weekday_preference"]=round(max(0.0,min(100.0,score)),1)
        if sp.weekend_preference != 0:
            cur=int(d.get("weekend_assignments",0) or 0)
            if _group_weekend_max==_group_weekend_min:
                score=100.0
            elif sp.weekend_preference>0:
                score=100.0*(cur-_group_weekend_min)/max(1,_group_weekend_max-_group_weekend_min)
            else:
                score=100.0*(_group_weekend_max-cur)/max(1,_group_weekend_max-_group_weekend_min)
            components["weekend_preference"]=round(max(0.0,min(100.0,score)),1)
        if sp.spread_preference != 0:
            spread01 = max(0.0, min(1.0, (d["dispersion_index"] - 0.5) / 0.5))
            score = 100.0 * spread01 if sp.spread_preference > 0 else 100.0 * (1.0 - spread01)
            components["spread_preference"] = round(score, 1)
        shift_len=max(0,min(3,int(getattr(sp,"shift_length_preference",0) or 0)))
        workstyle_proof=None
        # Count actual 12 h workdays as non-Onko days containing >=2 normal shifts.
        _normal_by_day={}
        _onko_days=set()
        for sl in pslots:
            if sl.department=="Onko RO centre":
                _onko_days.add(int(sl.day))
                continue
            _normal_by_day[int(sl.day)]=_normal_by_day.get(int(sl.day),0)+1
        _double_days=sum(1 for nday in _normal_by_day.values() if nday>=2)
        _single_days=sum(1 for nday in _normal_by_day.values() if nday==1)

        if shift_len==1 or (shift_len==0 and sp.avoid_doubles):
            # Prefer 6 h: requester should be at the low edge of the group's
            # unavoidable double pool. Allow a one-day corridor for feasibility.
            _threshold=min(_group_double_max,_group_double_min+1)
            fulfilled_ws=bool(_double_days<=_threshold)
            score=100.0 if fulfilled_ws else max(0.0,100.0-25.0*(_double_days-_threshold))
            components["shift_length_preference" if shift_len else "avoid_doubles"] = round(score,1)
            workstyle_proof={
                "mode":1,"requested":"PREFER_6H","frozen_input":True,
                "double_days":int(_double_days),"single_days":int(_single_days),
                "onko_9h_days":len(_onko_days),"group_double_min":int(_group_double_min),
                "group_double_max":int(_group_double_max),"fulfilled_threshold_max":int(_threshold),
            }
        elif shift_len==3:
            # Prefer 12 h: requester should be at the upper edge of the frozen
            # group double pool. A one-day corridor prevents false failure when
            # equally prioritized 12 h requesters must split an odd remainder.
            _threshold=max(_group_double_min,_group_double_max-1)
            fulfilled_ws=bool(_double_days>=_threshold)
            score=100.0 if fulfilled_ws else max(0.0,100.0-25.0*(_threshold-_double_days))
            components["shift_length_preference"] = round(score,1)
            workstyle_proof={
                "mode":3,"requested":"PREFER_12H","frozen_input":True,
                "double_days":int(_double_days),"single_days":int(_single_days),
                "onko_9h_days":len(_onko_days),"group_double_min":int(_group_double_min),
                "group_double_max":int(_group_double_max),"fulfilled_threshold_min":int(_threshold),
                "prefer12_cohort_size":len(_pref12_names),
                "prefer12_people":list(_pref12_names),
            }
        elif shift_len==2:
            by_day_normal={}
            for sl in pslots:
                if sl.department=="Onko RO centre":
                    continue
                by_day_normal[sl.day]=by_day_normal.get(sl.day,0)+1
            mixed_doubles=sum(1 for n in by_day_normal.values() if n>=2)
            mixed_singles=sum(1 for n in by_day_normal.values() if n==1)
            denom=max(1,mixed_doubles+mixed_singles)
            _mix_diff=abs(mixed_doubles-mixed_singles)
            # One-day difference is the mathematically closest possible 50/50 mix
            # when the number of normal workdays is odd, so count it as fully met.
            score=100.0 if _mix_diff<=1 else 100.0*max(0.0,1.0-(_mix_diff-1)/denom)
            components["shift_length_preference"] = round(score,1)
            workstyle_proof={
                "mode":2,"requested":"MIXED_6H_12H","frozen_input":True,
                "double_days":int(_double_days),"single_days":int(_single_days),
                "onko_9h_days":len(_onko_days),
            }

        if workstyle_proof is not None:
            d["workstyle_proof"]=dict(workstyle_proof)

        if sp.holiday_preference and public_holiday_days_in_month(year,month):
            hcount=sum(1 for sl in pslots if is_public_holiday(year,month,sl.day))
            components["holiday_preference"] = 100.0 if ((sp.holiday_preference>0 and hcount>0) or (sp.holiday_preference<0 and hcount==0)) else 0.0
        directional_keys={"weekday_preference","weekend_preference","spread_preference","shift_length_preference","avoid_doubles","holiday_preference"}
        directional_values=[v for k,v in components.items() if k in directional_keys]
        d["directional_preference_score"]=(
            round(float(np.mean(directional_values)),1) if directional_values else None
        )
        d["preference_components"] = components

        items=[dict(x) for x in (sp.request_items or [])]
        if not items:
            items=_fallback_request_items(sp,year,month)

        # For malformed/imported ledgers, whole-day RESIDENT HARD subsumes same-day
        # half-day entries. This mirrors the solver's one-human-request semantics.
        full_rh={int(x.get("day")) for x in items if x.get("kind")=="resident_hard" and x.get("block","FULL")=="FULL" and x.get("day")}
        detail_rows=[]
        category_values={}
        resident_hard_requested=resident_hard_honored=0
        absolute_requested=absolute_honored=0
        soft_exact_values=[]

        def overlapping(day,block):
            if day is None:
                return []
            return [s for s in pslots if s.day==int(day) and (block=="FULL" or blocks_overlap(s.block,block))]

        def overlapping_completed_covers(day,block):
            """Real ACTUAL cover only; theoretical standby is deliberately ignored."""
            if day is None:
                return []
            return [
                br for br in backup_rows
                if br.get("completed_at")
                and br.get("backup")==p.initials and int(br.get("day"))==int(day)
                and (block=="FULL" or blocks_overlap(str(br.get("block")),block))
            ]

        for ix,item in enumerate(items):
            kind=str(item.get("kind") or "")
            tier=str(item.get("tier") or "SOFT2_POSITIVE_PLACEMENT")
            block=str(item.get("block") or "FULL")
            day=item.get("day")
            day=int(day) if day not in (None,"") else None
            if kind=="resident_hard" and block in ("AM","PM") and day in full_rh:
                continue
            included=bool(item.get("included_in_score", tier not in ("ABSOLUTE_HARD","INFO")))
            source=str(item.get("source") or "effective")
            fulfilled=True
            score_value=100.0
            assigned_here=[]
            backup_here=[]
            category=None

            if kind=="resident_hard":
                assigned_here=overlapping(day,block)
                backup_here=overlapping_completed_covers(day,block)
                fulfilled=not bool(assigned_here or backup_here)
                score_value=100.0 if fulfilled else 0.0
                category="resident_hard"
                resident_hard_requested+=1
                resident_hard_honored+=int(fulfilled)
            elif kind=="soft_free":
                assigned_here=overlapping(day,block)
                backup_here=overlapping_completed_covers(day,block)
                fulfilled=not bool(assigned_here or backup_here)
                score_value=100.0 if fulfilled else 0.0
                category="soft1"
                soft_exact_values.append(score_value)
            elif kind=="preferred":
                assigned_here=overlapping(day,block)
                fulfilled=bool(assigned_here)
                score_value=100.0 if fulfilled else 0.0
                category="soft2"
                soft_exact_values.append(score_value)
            elif kind in directional_keys:
                score_value=float(components.get(kind,100.0))
                fulfilled=bool(score_value>=99.95)
                if kind in ("avoid_doubles","shift_length_preference") and int(item.get("value") or 0)==1:
                    category="soft1"
                else:
                    category="holiday" if kind=="holiday_preference" else "soft3"
            elif kind=="backup_claim":
                # Once backup rows are available, a self-selected commitment is
                # honored only if that exact covered slot is still assigned to this
                # resident. Before publication, fall back to the solver reservation
                # guarantee (free from overlapping normal work).
                assigned_here=overlapping(day,block)
                claimed_sid=item.get("covered_slot")
                if backup_assignments is not None and claimed_sid is not None:
                    matching=[br for br in backup_rows if br.get("covered_slot")==int(claimed_sid) and br.get("backup")==p.initials]
                    backup_here=matching
                    fulfilled=bool(matching) and not bool(assigned_here)
                else:
                    fulfilled=not bool(assigned_here)
                score_value=100.0 if fulfilled else 0.0
                category="backup_claim"
            elif kind=="rest_credit":
                # Invalid redemptions are blocked before generation. A valid frozen
                # redemption is therefore an explicit honored entitlement.
                fulfilled=True
                score_value=100.0
                category="rest_credit"
            elif kind=="vacation":
                assigned_here=overlapping(day,"FULL")
                fulfilled=not bool(assigned_here)
                score_value=100.0 if fulfilled else 0.0
                absolute_requested+=1; absolute_honored+=int(fulfilled)
                included=False
            elif kind=="justified_absence":
                assigned_here=overlapping(day,"FULL")
                fulfilled=not bool(assigned_here)
                score_value=100.0 if fulfilled else 0.0
                absolute_requested+=1; absolute_honored+=int(fulfilled)
                included=False
            elif kind=="long_duty":
                next_day=(day+1) if day is not None else None
                assigned_here=overlapping(next_day,"FULL") if next_day else []
                fulfilled=not bool(assigned_here)
                score_value=100.0 if fulfilled else 0.0
                absolute_requested+=1; absolute_honored+=int(fulfilled)
                included=False
            elif kind=="note":
                included=False
                fulfilled=True
                score_value=100.0
            else:
                included=False

            if included and category:
                category_values.setdefault(category,[]).append(float(score_value))

            station_parts=[]
            if assigned_here:
                station_parts.extend(
                    f"{sl.department} ({sl.block})" for sl in sorted(assigned_here,key=lambda z:(z.day,z.idx))
                )
            if backup_here:
                if kind=="backup_claim":
                    station_parts.extend(
                        f"TEORINIS DUBLIS → {br.get('department')} ({br.get('block')})" for br in backup_here
                    )
                else:
                    station_parts.extend(
                        f"REALIAI PAVADAVO → {br.get('department')} ({br.get('block')})" for br in backup_here
                    )
            station_text="; ".join(station_parts) if station_parts else "—"
            if kind in ("shift_length_preference","avoid_doubles") and workstyle_proof:
                station_text=(
                    f"12 h dienos: {workstyle_proof.get('double_days',0)}; "
                    f"6 h dienos: {workstyle_proof.get('single_days',0)}; "
                    f"Onko 9 h: {workstyle_proof.get('onko_9h_days',0)}"
                )
                if int(workstyle_proof.get("mode",0))==3:
                    station_text+=(
                        f"; grupės dublių intervalas {_group_double_min}–{_group_double_max}; "
                        f"12 h pageidavimo išpildymo riba ≥{workstyle_proof.get('fulfilled_threshold_min',0)}"
                    )
            if station_text=="—" and kind=="backup_claim" and item.get("department"):
                station_text=str(item.get("department"))

            if kind in ("resident_hard","soft_free") and not fulfilled:
                swap_hint=f"Swap away this assignment: {station_text}"
            elif kind=="preferred" and not fulfilled:
                swap_hint=f"Look for an eligible assignment on {day} ({block})"
            elif kind=="resident_hard":
                swap_hint="—"
            elif not fulfilled:
                swap_hint="Review in Apsikeitimai / Swaps"
            else:
                swap_hint="—"

            detail_rows.append({
                "request_id":str(item.get("id") or f"{p.initials}:{ix}:{kind}:{day}:{block}"),
                "priority":tier,
                "type":_request_kind_label(kind),
                "kind":kind,
                "source":source,
                "date":date(year,month,day).isoformat() if day and 1<=day<=ndays else "—",
                "day":day,
                "block":block,
                "station":station_text,
                "requested_value":item.get("value"),
                "fulfilled":bool(fulfilled),
                "score":round(float(score_value),1),
                "included_in_score":bool(included),
                "swap_hint":swap_hint,
                "workstyle_proof":dict(workstyle_proof) if kind in ("shift_length_preference","avoid_doubles") and workstyle_proof else None,
                "input_snapshot":"FROZEN_SYSTEM_REQUEST_SNAPSHOT" if kind in ("shift_length_preference","avoid_doubles") else None,
            })

        category_scores={
            k:round(float(np.mean(v)),1) for k,v in category_values.items() if v
        }
        active_category_scores=list(category_scores.values())
        overall_request_score=(
            round(float(np.mean(active_category_scores)),1) if active_category_scores else None
        )
        soft_category_scores=[category_scores[k] for k in ("soft1","soft2","soft3") if k in category_scores]
        soft_preference_score=(
            round(float(np.mean(soft_category_scores)),1) if soft_category_scores else None
        )
        resident_hard_score=(
            round(100.0*resident_hard_honored/resident_hard_requested,1)
            if resident_hard_requested else None
        )
        absolute_score=(
            round(100.0*absolute_honored/absolute_requested,1)
            if absolute_requested else None
        )

        d["resident_hard_requested"]=int(resident_hard_requested)
        d["resident_hard_honored"]=int(resident_hard_honored)
        d["resident_hard_losses"]=int(resident_hard_requested-resident_hard_honored)
        d["resident_hard_score"]=resident_hard_score
        d["prior_resident_hard_loss_count"]=int(getattr(sp,"prior_resident_hard_loss_count",0) or 0)
        d["cumulative_resident_hard_losses"]=d["prior_resident_hard_loss_count"]+d["resident_hard_losses"]
        d["absolute_hard_requested"]=int(absolute_requested)
        d["absolute_hard_honored"]=int(absolute_honored)
        d["absolute_hard_accommodation_score"]=absolute_score
        d["soft_preference_score"]=soft_preference_score
        d["request_category_scores"]=category_scores
        d["overall_request_score"]=overall_request_score
        # Backward-compatible UI key now intentionally means COMPLETE resident
        # request satisfaction, not SOFT-only satisfaction.
        d["preference_score"]=overall_request_score
        d["request_score_method"]="V2553_WHITELIST_CATEGORY_NORMALIZED_WEEKLY_RECOVERY_WATERFILL"
        d["request_detail_rows"]=detail_rows
        d["unhonored_request_details"]=[r for r in detail_rows if r["included_in_score"] and not r["fulfilled"]]
        d["resident_hard_conflicts"]=[r for r in detail_rows if r["kind"]=="resident_hard" and not r["fulfilled"]]
        d["soft_request_misses"]=[r for r in detail_rows if r["priority"].startswith("SOFT") and not r["fulfilled"]]
        d["honored_request_details"]=[r for r in detail_rows if r["included_in_score"] and r["fulfilled"]]

    # V2.5.77 ABSOLUTE SYSTEM Friday water-fill. This is generation-only:
    # post-publication mutually accepted ACTUAL swaps may intentionally make the
    # Friday distribution uneven, just like workplace exposure.
    friday_structural_vals=[int(v.get("friday_assignments",0) or 0) for v in pdata.values()]
    friday_structural_spread=(max(friday_structural_vals)-min(friday_structural_vals)) if friday_structural_vals else 0
    friday_structural_total=int(sum(friday_structural_vals))
    friday_structural_n=max(1,len(friday_structural_vals))
    friday_structural_floor=int(friday_structural_total//friday_structural_n)
    friday_structural_ceil=int((friday_structural_total+friday_structural_n-1)//friday_structural_n)
    friday_structural_entitlement_gate=bool(
        friday_structural_vals
        and all(friday_structural_floor <= int(v) <= friday_structural_ceil for v in friday_structural_vals)
        and friday_structural_spread<=1
    )
    if (not voluntary_swap_mode) and not friday_structural_entitlement_gate:
        structural_warnings.append(
            "Friday structural water-fill target not reached: "
            f"total {friday_structural_total} across {len(friday_structural_vals)} residents normally targets "
            f"{friday_structural_floor}-{friday_structural_ceil} each, observed "
            f"{min(friday_structural_vals) if friday_structural_vals else 0}-"
            f"{max(friday_structural_vals) if friday_structural_vals else 0} "
            f"(raw spread {friday_structural_spread})"
        )

    # Group fairness metrics.
    def spread_of(key):
        vals = [v[key] for v in pdata.values()]
        return (max(vals) - min(vals)) if vals else 0

    def volunteer_neutral_spread(key):
        """Return avoidable spread after removing mathematically unavoidable 0/1 spread.

        When volunteers absorb unpopular shifts, the remaining non-voluntary load
        may no longer divide evenly by the group size. A perfectly optimized
        distribution can then have a raw max-min spread of 1. That unavoidable
        remainder must not be reported as a fairness loss caused by volunteering.
        """
        vals = [v[key] for v in pdata.values()]
        if not vals:
            return 0, 0, 0
        raw = max(vals) - min(vals)
        total = int(round(sum(vals)))
        unavoidable = 0 if total % len(vals) == 0 else 1
        return max(0, raw - unavoidable), raw, unavoidable

    # Current selected month only. Weekend exposure intentionally includes ALL
    # assigned weekends (including preferred/voluntary dates), because V2.5.52
    # treats weekend count as a fatigue/exposure safeguard. The legacy 0–100
    # summary still removes the mathematically unavoidable 0/1 remainder; the
    # constitutional CRITICAL gate below uses the raw weekend spread.
    monthly_weekend_spread, monthly_weekend_spread_raw, monthly_weekend_unavoidable = volunteer_neutral_spread("fairness_weekend_assignments")
    monthly_friday_spread, monthly_friday_spread_raw, monthly_friday_unavoidable = volunteer_neutral_spread("fairness_friday_assignments")
    monthly_double_spread = spread_of("doubles")
    monthly_weekday_day_spread = spread_of("weekday_days")
    saturday_monthly_spread_raw = spread_of("saturdays")
    sunday_monthly_spread_raw = spread_of("sundays")
    saturday_monthly_spread = spread_of("fairness_saturdays")
    sunday_monthly_spread = spread_of("fairness_sundays")

    # Prior published SYSTEM history + current selected month.
    cumulative_weekend_spread, cumulative_weekend_spread_raw, cumulative_weekend_unavoidable = volunteer_neutral_spread("cumulative_fair_weekend_count")
    cumulative_friday_spread, cumulative_friday_spread_raw, cumulative_friday_unavoidable = volunteer_neutral_spread("cumulative_friday_count")
    cumulative_double_spread = spread_of("cumulative_double_count")
    cumulative_weekday_day_spread = spread_of("cumulative_weekday_day_count")

    def fairness_score_from_spreads(w, f, d, wd):
        return max(
            0.0,
            100.0
            - 18.0 * w
            - 7.0 * f
            - 4.0 * d
            - 2.0 * wd
        )

    monthly_fairness_score = fairness_score_from_spreads(
        monthly_weekend_spread,
        monthly_friday_spread,
        monthly_double_spread,
        monthly_weekday_day_spread,
    )
    cumulative_fairness_score = fairness_score_from_spreads(
        cumulative_weekend_spread,
        cumulative_friday_spread,
        cumulative_double_spread,
        cumulative_weekday_day_spread,
    )

    # Rotation diversity / longitudinal workplace exposure balance.
    rotation_monthly_spreads={}
    rotation_cumulative_spreads={}
    rotation_monthly_normalized_spreads={}
    for cat in ROTATION_CATEGORIES:
        mv=[int(v["rotation_counts"].get(cat,0)) for v in pdata.values()]
        cv=[int(v["cumulative_rotation_counts"].get(cat,0)) for v in pdata.values()]
        rotation_monthly_spreads[cat]=(max(mv)-min(mv)) if mv else 0
        rotation_cumulative_spreads[cat]=(max(cv)-min(cv)) if cv else 0
        norm=[]
        for initials,v in pdata.items():
            denom=max(1.0,float(v.get("target",0) or 0))
            norm.append(float(v["rotation_counts"].get(cat,0))/denom)
        rotation_monthly_normalized_spreads[cat]=(max(norm)-min(norm)) if norm else 0.0
    distinct_rotation_values=[int(v["distinct_rotations"]) for v in pdata.values()]
    mean_distinct_rotations=(float(np.mean(distinct_rotation_values)) if distinct_rotation_values else 0.0)
    distinct_rotation_spread=(max(distinct_rotation_values)-min(distinct_rotation_values)) if distinct_rotation_values else 0
    rotation_monthly_imbalance=sum(rotation_monthly_spreads.values())
    rotation_cumulative_imbalance=sum(rotation_cumulative_spreads.values())
    worst_monthly_post_spread=max(list(rotation_monthly_spreads.values())+[0])
    worst_monthly_normalized_post_spread=max(list(rotation_monthly_normalized_spreads.values())+[0.0])

    # V2.5.90 critical structural quality.
    # In baseline volunteer mode, SPS RO/weekend gate values are fairness-adjusted;
    # raw values remain separately visible for full transparency.
    _fair_sps_vals=[int(v.get("fairness_sps_ro_assignments",0) or 0) for v in pdata.values()]
    _raw_sps_vals=[int((v.get("rotation_counts") or {}).get("SPS RO",0) or 0) for v in pdata.values()]
    _raw_weekend_vals=[int(v.get("weekend_assignments",0) or 0) for v in pdata.values()]
    _fair_sps_spread=(max(_fair_sps_vals)-min(_fair_sps_vals)) if _fair_sps_vals else 0
    _raw_sps_spread=(max(_raw_sps_vals)-min(_raw_sps_vals)) if _raw_sps_vals else 0
    _raw_weekend_spread=(max(_raw_weekend_vals)-min(_raw_weekend_vals)) if _raw_weekend_vals else 0

    critical_structural_spreads={
        "SPS RO":int(_fair_sps_spread),
        "SPS UG":int(rotation_monthly_spreads.get("SPS UG",0)),
        "SATURDAYS":int(saturday_monthly_spread),
        "SUNDAYS":int(sunday_monthly_spread),
        "FRIDAYS":int(friday_structural_spread),
    }
    critical_structural_spreads_raw={
        "SPS RO":int(_raw_sps_spread),
        "SPS UG":int(rotation_monthly_spreads.get("SPS UG",0)),
        "SATURDAYS":int(saturday_monthly_spread_raw),
        "SUNDAYS":int(sunday_monthly_spread_raw),
        "FRIDAYS":int(friday_structural_spread),
    }
    if (not voluntary_swap_mode) and saturday_monthly_spread>1:
        structural_warnings.append(f"Saturday water-fill target not reached: spread {saturday_monthly_spread} > 1")
    if (not voluntary_swap_mode) and sunday_monthly_spread>1:
        structural_warnings.append(f"Sunday water-fill target not reached: spread {sunday_monthly_spread} > 1")

    critical_worst_spread=max(list(critical_structural_spreads.values())+[0])
    critical_worst_spread_raw=max(list(critical_structural_spreads_raw.values())+[0])
    noncritical_post_spreads={cat:int(rotation_monthly_spreads.get(cat,0)) for cat in NONCRITICAL_ROTATION_CATEGORIES}
    noncritical_worst_spread=max(list(noncritical_post_spreads.values())+[0])
    critical_spread_quality_gate_passed=bool(critical_worst_spread<=CRITICAL_SPREAD_TARGET)
    noncritical_normal_guardrail_passed=bool(noncritical_worst_spread<=NONCRITICAL_SPREAD_NORMAL_CEILING)
    noncritical_exceptional_guardrail_passed=bool(noncritical_worst_spread<=NONCRITICAL_SPREAD_EXCEPTIONAL_CEILING)
    noncritical_last_resort_guardrail_passed=bool(noncritical_worst_spread<=NONCRITICAL_SPREAD_LAST_RESORT_CEILING)
    # V2.5.74: ordinary post target is raw spread <=1. validate_schedule can report
    # the observed matrix; solve_schedule is responsible for proving whether a
    # wider certified corridor was unavoidable before returning a SYSTEM draft.
    post_spread_quality_gate_passed=bool(critical_spread_quality_gate_passed and noncritical_last_resort_guardrail_passed)

    # V2.5.53 weekly-load / recovery diagnostics. These are separate from the
    # legacy 0-100 fairness score because they are safety/temporal-burden metrics.
    all_week_keys=sorted({wk for v in pdata.values() for wk in (v.get("weekly_hours") or {}).keys()})
    calendar_week_hour_spreads={}
    for wk in all_week_keys:
        vals=[float((v.get("weekly_hours") or {}).get(wk,0.0)) for v in pdata.values()]
        calendar_week_hour_spreads[wk]=round((max(vals)-min(vals)) if vals else 0.0,1)
    worst_calendar_week_hour_spread=max(list(calendar_week_hour_spreads.values())+[0.0])
    max_rolling7_hours_observed=max([float(v.get("max_rolling7_hours",0.0) or 0.0) for v in pdata.values()]+[0.0])
    max_calendar_week_hours_observed=max([float(v.get("max_calendar_week_hours",0.0) or 0.0) for v in pdata.values()]+[0.0])
    residents_over40_rolling7=sum(1 for v in pdata.values() if float(v.get("max_rolling7_hours",0.0) or 0.0)>WEEKLY_LOAD_SOFT_TARGET_HOURS+1e-9)
    consecutive_double_pairs_total=sum(int(v.get("consecutive_double_pairs",0) or 0) for v in pdata.values())
    worked_after_two_doubles_total=sum(int(v.get("worked_after_two_doubles",0) or 0) for v in pdata.values())
    effective_global_hours_ceiling=(
        min(float(rule_value("swap_max_hours_rolling7")),float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7)) if voluntary_swap_mode
        else min(float(rule_value("max_hours_rolling7")),float(FATIGUE_ROLLING7_HARD_CEILING_HOURS))
    )
    weekly_load_safety_gate_passed=bool(
        all(
            float(v.get("max_rolling7_hours",0.0) or 0.0)
            <= (effective_global_hours_ceiling if voluntary_swap_mode else max(effective_global_hours_ceiling,float(weekly_hours_override_caps.get(initials,effective_global_hours_ceiling)))) + 1e-9
            for initials,v in pdata.items()
        )
        and all(int(v.get("max_consecutive_days",0) or 0)<=SWAP_MAX_WORKDAYS_ROLLING7 for v in pdata.values())
    )

    # V2.5.96: post debt / future fairness catch-up is retired.
    # Keep the key for backward-compatible payload readers, but it is always zero
    # and is never consumed by the solver.
    cumulative_means={cat: 0.0 for cat in ROTATION_CATEGORIES}
    for initials,d in pdata.items():
        d["post_debt"]={cat:0.0 for cat in ROTATION_CATEGORIES}

    # V2.5.37 DISPLAY FAIRNESS = CURRENT ENGINE CRITERIA, not the legacy
    # 100-18w-7f-4d-2wd formula that could floor a populated schedule to 0%.
    # A spread of 0 is ideal; spread 1 is treated as near-ideal/unavoidable for
    # discrete group allocation in doubles, workdays and workplace counts.
    def _spread_component(spread, allow_one=False):
        # Interpretable quality scale: 100 = ideal/near-ideal. Every additional
        # avoidable spread unit costs 3 points inside that component. This keeps
        # the displayed percentage calibrated like the original ~90% range rather
        # than collapsing normal schedules to 0–10%.
        excess=max(0.0,float(spread)-(1.0 if allow_one else 0.0))
        return max(0.0,100.0-3.0*excess)

    monthly_post_score=float(np.mean([
        _spread_component(v,allow_one=True) for v in rotation_monthly_spreads.values()
    ])) if rotation_monthly_spreads else 100.0
    cumulative_post_score=float(np.mean([
        _spread_component(v,allow_one=True) for v in rotation_cumulative_spreads.values()
    ])) if rotation_cumulative_spreads else 100.0

    monthly_fairness_score_balanced=(
        0.50*monthly_post_score
        +0.15*_spread_component(monthly_weekend_spread)
        +0.10*_spread_component(monthly_friday_spread)
        +0.10*_spread_component(monthly_double_spread,allow_one=True)
        +0.15*_spread_component(monthly_weekday_day_spread,allow_one=True)
    )
    cumulative_fairness_score_balanced=(
        0.50*cumulative_post_score
        +0.15*_spread_component(cumulative_weekend_spread)
        +0.10*_spread_component(cumulative_friday_spread)
        +0.10*_spread_component(cumulative_double_spread,allow_one=True)
        +0.15*_spread_component(cumulative_weekday_day_spread,allow_one=True)
    )

    legacy_monthly_fairness_score=monthly_fairness_score
    legacy_cumulative_fairness_score=cumulative_fairness_score
    monthly_fairness_score=monthly_fairness_score_balanced
    cumulative_fairness_score=cumulative_fairness_score_balanced

    active_scores = [v["preference_score"] for v in pdata.values() if v["preference_score"] is not None]
    active_soft_scores=[v["soft_preference_score"] for v in pdata.values() if v.get("soft_preference_score") is not None]
    active_exact_scores=[v["exact_preference_score"] for v in pdata.values() if v.get("exact_preference_score") is not None]
    preference_score_spread=(float(max(active_scores)-min(active_scores)) if active_scores else None)
    soft_preference_score_spread=(float(max(active_soft_scores)-min(active_soft_scores)) if active_soft_scores else None)
    # Equity target is applied to NEGOTIABLE SOFT satisfaction. RESIDENT-HARD
    # burden is optimized in its own higher-priority minimax layer.
    preference_equity_quality_gate_passed=(
        None if len(active_soft_scores)<2 else bool(soft_preference_score_spread<=15.0+1e-9)
    )
    rh_losses=[int(v.get("resident_hard_losses",0) or 0) for v in pdata.values()]
    rh_cumulative=[int(v.get("cumulative_resident_hard_losses",0) or 0) for v in pdata.values()]
    resident_hard_total_losses=sum(rh_losses)
    resident_hard_residents_affected=sum(1 for x in rh_losses if x>0)
    resident_hard_max_loss=max(rh_losses) if rh_losses else 0
    resident_hard_loss_spread=(max(rh_losses)-min(rh_losses)) if rh_losses else 0
    resident_hard_cumulative_spread=(max(rh_cumulative)-min(rh_cumulative)) if rh_cumulative else 0
    resident_hard_backup_conflicts=sum(
        1 for v in pdata.values() for r in (v.get("resident_hard_conflicts") or [])
        if "REALIAI PAVADAVO" in str(r.get("station") or "")
    )
    soft_backup_misses=sum(
        1 for v in pdata.values() for r in (v.get("soft_request_misses") or [])
        if "REALIAI PAVADAVO" in str(r.get("station") or "")
    )

    return {
        "global": {
            "hard_errors": len(errors),
            "errors": errors,
            "backup_layer_hard_errors": len(backup_layer_errors),
            "backup_layer_errors": list(backup_layer_errors),
            "backup_layer_valid": (len(backup_layer_errors)==0),
            "backup_layer_semantics": "THEORETICAL_STANDBY_UNTIL_COMPLETED",
            "planned_backups_affect_request_score": False,
            "activated_backups_affect_request_score": False,
            "completed_backups_affect_actual_request_score": True,
            "structural_warnings": structural_warnings,
            "structural_warning_count": int(len(structural_warnings)),
            "exact_workload_targets_required": True,
            "exact_workload_targets_passed": all(abs(float(v.get("workload_target_delta",0.0) or 0.0)) <= 1e-9 for v in pdata.values()),
            "onko_even_pairs_required": True,
            "onko_even_pairs_absolute_all_modes": True,
            "onko_even_pairs_passed": all(int(v.get("rotation_counts",{}).get("Onko RO",0) or 0) % 2 == 0 for v in pdata.values()),
            "onko_active_slot_count": len(onko_slots),
            "onko_expected_filled_count": expected_onko,
            "onko_actual_filled_count": onko_filled,
            "onko_parity_gap_required": bool(len(onko_slots) % 2 == 1),
            "onko_monthly_spread_ceiling": 2,
            "weekday_count": weekday_count(year, month),
            "base_target": standard_target(year, month),
            "weekly_load_model":"V2555_GENERATION_48H_RECOVERY_STRICT__VOLUNTARY_SWAP_12H_11H_6D_60H_REALITY_GUARD",
            "validation_mode":str(validation_mode),
            "voluntary_swap_mode":bool(voluntary_swap_mode),
            "swap_absolute_max_hours_rolling7":float(min(float(rule_value("swap_max_hours_rolling7")),float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7))),
            "swap_max_workdays_rolling7":int(SWAP_MAX_WORKDAYS_ROLLING7),
            "swap_min_daily_rest_hours":float(SWAP_MIN_DAILY_REST_HOURS),
            "swap_max_hours_per_day":float(SWAP_MAX_HOURS_PER_DAY),
            "swap_weekly_rest_proxy_hours":float(SWAP_WEEKLY_REST_PROXY_HOURS),
            "swap_weekly_hours_override_caps":{k:round(float(v),1) for k,v in weekly_hours_override_caps.items()},
            "swap_weekly_hours_override_active":bool(weekly_hours_override_caps),
            "swap_weekly_hours_override_residents":sorted(weekly_hours_override_caps),
            "swap_weekly_hours_override_window_count":int(sum(len(v.get("weekly48_override_windows") or []) for v in pdata.values())),
            "weekly_load_soft_target_hours":float(WEEKLY_LOAD_SOFT_TARGET_HOURS),
            "weekly_load_hard_ceiling_hours":float(effective_global_hours_ceiling),
            "weekly_load_max_workdays_rolling7":int(SWAP_MAX_WORKDAYS_ROLLING7 if voluntary_swap_mode else min(int(rule_value("max_workdays_rolling7")),int(FATIGUE_MAX_WORKDAYS_ROLLING7))),
            "max_rolling7_hours_observed":round(float(max_rolling7_hours_observed),1),
            "max_calendar_week_hours_observed":round(float(max_calendar_week_hours_observed),1),
            "calendar_week_hour_spreads":calendar_week_hour_spreads,
            "worst_calendar_week_hour_spread":round(float(worst_calendar_week_hour_spread),1),
            "residents_over40_rolling7":int(residents_over40_rolling7),
            "consecutive_double_pairs_total":int(consecutive_double_pairs_total),
            "worked_after_two_doubles_total":int(worked_after_two_doubles_total),
            "weekly_load_safety_gate_passed":bool(weekly_load_safety_gate_passed),
            "weekend_monthly_spread": monthly_weekend_spread,
            # Backward-compatible "raw" now means the actually visible/raw worked
            # weekend count, while the new adjusted key is the fairness-gate input.
            "weekend_monthly_spread_raw": int(_raw_weekend_spread),
            "saturday_monthly_spread": int(saturday_monthly_spread),
            "sunday_monthly_spread": int(sunday_monthly_spread),
            "saturday_monthly_spread_raw": int(saturday_monthly_spread_raw),
            "sunday_monthly_spread_raw": int(sunday_monthly_spread_raw),
            "weekend_fairness_spread_adjusted_raw": int(monthly_weekend_spread_raw),
            "weekend_monthly_unavoidable_spread": monthly_weekend_unavoidable,
            "weekend_volunteer_adjustment_active": bool(_baseline_weekend_volunteer_mode),
            "friday_monthly_spread": monthly_friday_spread,
            "friday_monthly_spread_raw": monthly_friday_spread_raw,
            "friday_monthly_unavoidable_spread": monthly_friday_unavoidable,
            "friday_structural_waterfill_required": True,
            "friday_structural_total_assignments": int(friday_structural_total),
            "friday_structural_resident_count": int(len(friday_structural_vals)),
            "friday_structural_entitlement_floor": int(friday_structural_floor),
            "friday_structural_entitlement_ceil": int(friday_structural_ceil),
            "friday_structural_spread_raw": int(friday_structural_spread),
            "friday_structural_spread_ceiling": 1,
            "friday_structural_gate_passed": bool(friday_structural_entitlement_gate),
            "double_monthly_spread": monthly_double_spread,
            "weekday_day_monthly_spread": monthly_weekday_day_spread,
            "weekend_cumulative_spread": cumulative_weekend_spread,
            "weekend_cumulative_spread_raw": cumulative_weekend_spread_raw,
            "weekend_cumulative_unavoidable_spread": cumulative_weekend_unavoidable,
            "friday_cumulative_spread": cumulative_friday_spread,
            "friday_cumulative_spread_raw": cumulative_friday_spread_raw,
            "friday_cumulative_unavoidable_spread": cumulative_friday_unavoidable,
            "double_cumulative_spread": cumulative_double_spread,
            "weekday_day_cumulative_spread": cumulative_weekday_day_spread,
            # Backward-compatible aliases now point to the PRIMARY cumulative metric.
            "friday_spread": cumulative_friday_spread,
            "double_spread": cumulative_double_spread,
            "weekday_day_spread": cumulative_weekday_day_spread,
            "monthly_fairness_score": round(monthly_fairness_score, 1),
            "cumulative_fairness_score": round(cumulative_fairness_score, 1),
            "fairness_score": round(cumulative_fairness_score, 1),
            "monthly_post_fairness_score": round(monthly_post_score,1),
            "cumulative_post_fairness_score": round(cumulative_post_score,1),
            "legacy_monthly_fairness_score": round(legacy_monthly_fairness_score,1),
            "legacy_cumulative_fairness_score": round(legacy_cumulative_fairness_score,1),
            "fairness_score_method": "V2550_2D_WATERFILL_REQUEST_FAIRNESS",
            "resident_hard_total_losses": int(resident_hard_total_losses),
            "resident_hard_residents_affected": int(resident_hard_residents_affected),
            "resident_hard_max_loss_per_resident": int(resident_hard_max_loss),
            "resident_hard_loss_spread": int(resident_hard_loss_spread),
            "resident_hard_cumulative_spread": int(resident_hard_cumulative_spread),
            "resident_hard_backup_conflicts": int(resident_hard_backup_conflicts),
            "soft_backup_misses": int(soft_backup_misses),
            "optional_gaps": optional_gap_rows,
            "optional_gap_count": len(optional_gap_rows),
            "optional_gap_category_counts": cat_gap_counts,
            "optional_gap_category_spread": optional_gap_category_spread,
            "expected_gap_days": expected_gap_days,
            "actual_gap_days": actual_gap_days,
            "mean_preference_score": round(float(np.mean(active_scores)), 1) if active_scores else None,
            "min_preference_score": round(float(min(active_scores)),1) if active_scores else None,
            "max_preference_score": round(float(max(active_scores)),1) if active_scores else None,
            "preference_score_spread": round(preference_score_spread,1) if preference_score_spread is not None else None,
            "active_preference_residents": int(len(active_scores)),
            "mean_soft_preference_score": round(float(np.mean(active_soft_scores)),1) if active_soft_scores else None,
            "min_soft_preference_score": round(float(min(active_soft_scores)),1) if active_soft_scores else None,
            "max_soft_preference_score": round(float(max(active_soft_scores)),1) if active_soft_scores else None,
            "soft_preference_score_spread": round(soft_preference_score_spread,1) if soft_preference_score_spread is not None else None,
            "active_soft_preference_residents": int(len(active_soft_scores)),
            "mean_exact_preference_score": round(float(np.mean(active_exact_scores)),1) if active_exact_scores else None,
            "min_exact_preference_score": round(float(min(active_exact_scores)),1) if active_exact_scores else None,
            "active_exact_preference_residents": int(len(active_exact_scores)),
            "mean_distinct_rotations": round(mean_distinct_rotations, 2),
            "distinct_rotation_spread": int(distinct_rotation_spread),
            "rotation_monthly_spreads": rotation_monthly_spreads,
            "rotation_monthly_normalized_spreads": {k:round(float(v),6) for k,v in rotation_monthly_normalized_spreads.items()},
            "rotation_cumulative_spreads": rotation_cumulative_spreads,
            "rotation_monthly_imbalance": int(rotation_monthly_imbalance),
            "rotation_cumulative_imbalance": int(rotation_cumulative_imbalance),
            "worst_monthly_post_spread": int(worst_monthly_post_spread),
            "worst_monthly_normalized_post_spread": round(float(worst_monthly_normalized_post_spread),6),
            "critical_structural_spreads":critical_structural_spreads,
            "critical_structural_spreads_raw":critical_structural_spreads_raw,
            "critical_worst_spread":int(critical_worst_spread),
            "critical_worst_spread_raw":int(critical_worst_spread_raw),
            "baseline_weekend_volunteer_mode":bool(_baseline_weekend_volunteer_mode),
            "weekend_volunteer_adjustment_policy":"V2.5.112 ADMIN: no volunteer exemption. SYSTEM uses raw Saturday/Sunday/total-weekend water-fill and locks the tightest feasible corridor before lower preferences; ACTUAL swaps may diverge only after the operational approval flow.",
            "critical_spread_quality_target":int(CRITICAL_SPREAD_TARGET),
            "critical_spread_quality_gate_passed":critical_spread_quality_gate_passed,
            "noncritical_post_spreads":noncritical_post_spreads,
            "noncritical_worst_spread":int(noncritical_worst_spread),
            "noncritical_normal_guardrail":int(NONCRITICAL_SPREAD_NORMAL_CEILING),
            "noncritical_exceptional_guardrail":int(NONCRITICAL_SPREAD_EXCEPTIONAL_CEILING),
            "noncritical_last_resort_guardrail":int(NONCRITICAL_SPREAD_LAST_RESORT_CEILING),
            "noncritical_normal_guardrail_passed":noncritical_normal_guardrail_passed,
            "noncritical_exceptional_guardrail_passed":noncritical_exceptional_guardrail_passed,
            "noncritical_last_resort_guardrail_passed":noncritical_last_resort_guardrail_passed,
            "post_waterfill_structural_target":1,
            "post_waterfill_categories":list(NONCRITICAL_ROTATION_CATEGORIES),
            "post_spread_quality_ceiling": int(NONCRITICAL_SPREAD_LAST_RESORT_CEILING),
            "post_spread_quality_gate_passed": post_spread_quality_gate_passed,
            "post_debt_cumulative_means":{k:round(v,2) for k,v in cumulative_means.items()},
            "preference_equity_quality_target_pp": 15.0,
            "preference_equity_quality_gate_passed": preference_equity_quality_gate_passed,
            "preference_fairness_model": "V2553_VERTICAL_RANK_HORIZONTAL_WEEKLY_RECOVERY_WATERFILL_GUARDRAILS",
            "preference_vertical_order": ["ABSOLUTE_HARD","RESIDENT_HARD_ZERO_LOSS","VOLUNTEER_ADJUSTED_CRITICAL_SPS_RO_SPS_UG_WEEKENDS_FRIDAYS","BASELINE_UNPOPULAR_WEEKEND_VOLUNTEERS","CRITICAL_SPACING","WEEKLY_LOAD_RECOVERY_WATERFILL","STRUCTURAL_BURDEN","NONCRITICAL_POST_GUARDRAIL","SOFT1","SOFT2","SOFT3","NONCRITICAL_POST_MONTHLY_OPTIMUM"],
            "post_fairness_model": "V2577_ALL_POST_PLUS_FRIDAY_STRUCTURAL_WATERFILL",
            "soft_waterfill_locks": {},
        },
        "people": pdata,
    }


def _swap_warning_rows(year: int, month: int, people: List[Person], before: SolveResult,
                       after_stats: Dict[str, dict], participants: Tuple[str, str]) -> Dict[str, List[dict]]:
    """Structured, resident-facing consequences of a voluntary swap.

    These rows are *not* blockers. They are the things a resident should consciously
    see before agreeing: a new 12h double, >40/>48h rolling load, six-day streak,
    post-double recovery pattern, or a newly self-overridden RESIDENT-HARD request.
    """
    out={str(i):[] for i in participants}
    before_people=(before.stats or {}).get("people",{})
    after_people=(after_stats or {}).get("people",{})
    for initials in participants:
        b=before_people.get(initials) or {}
        a=after_people.get(initials) or {}
        rows=[]
        bdouble=set(int(x) for x in (b.get("double_days") or []))
        adouble=set(int(x) for x in (a.get("double_days") or []))
        for day in sorted(adouble-bdouble):
            rows.append({
                "severity":"ACK","kind":"12H_DOUBLE","date":f"{year:04d}-{month:02d}-{day:02d}",
                "before":"1 pamaina / laisva","after":"2 × 6 h = 12 h",
                "explanation":"Po swapo ši diena tampa dviguba 12 val. darbo diena."
            })
        b40=float(b.get("max_rolling7_hours",0.0) or 0.0)
        a40=float(a.get("max_rolling7_hours",0.0) or 0.0)
        if a40>WEEKLY_LOAD_SOFT_TARGET_HOURS+1e-9 and a40>b40+1e-9:
            rows.append({
                "severity":"ACK","kind":"WEEKLY_LOAD","date":"7 d. langas",
                "before":f"{b40:g} h max","after":f"{a40:g} h max",
                "explanation":f"Viršijamas generatoriaus ~{WEEKLY_LOAD_SOFT_TARGET_HOURS:g} h/7 d. planavimo tikslas."
            })
        if a40>FATIGUE_ROLLING7_HARD_CEILING_HOURS+1e-9 and a40>b40+1e-9:
            rows.append({
                "severity":"ACK","kind":"OVER_48H","date":"7 d. langas",
                "before":f"{b40:g} h max","after":f"{a40:g} h max",
                "explanation":"Virš 48 h generatoriaus ribos. Savanoriškam swapui leidžiama tik su aiškiu sutikimu; absoliutus 60 h/7 d. blokas lieka."
            })
        bcon=int(b.get("max_consecutive_days",0) or 0); acon=int(a.get("max_consecutive_days",0) or 0)
        if acon>=6 and acon>bcon:
            rows.append({
                "severity":"ACK","kind":"SIX_DAY_STREAK","date":"darbo seka",
                "before":str(bcon),"after":str(acon),
                "explanation":"Susidaro 6 darbo dienų seka. 7-a darbo diena neleidžiama — po šešių turi likti poilsio diena."
            })
        bpair=int(b.get("consecutive_double_pairs",0) or 0); apair=int(a.get("consecutive_double_pairs",0) or 0)
        if apair>bpair:
            rows.append({
                "severity":"ACK","kind":"CONSECUTIVE_DOUBLES","date":"dvigubų seka",
                "before":str(bpair),"after":str(apair),
                "explanation":"Swapas sukuria papildomą dviejų dvigubų dienų seką; tai nebeblokuoja savanoriško swapo, bet rodoma kaip nuovargio rizika."
            })
        b_onko_pairs=list(b.get("consecutive_onko_pairs") or [])
        a_onko_pairs=list(a.get("consecutive_onko_pairs") or [])
        if len(a_onko_pairs)>len(b_onko_pairs):
            def _fmt_onko_pair(pair):
                try:
                    x,y=int(pair[0]),int(pair[1])
                    if x==0:
                        return f"ankstesnio mėn. paskutinė d. → {year:04d}-{month:02d}-{y:02d}"
                    return f"{year:04d}-{month:02d}-{x:02d} → {year:04d}-{month:02d}-{y:02d}"
                except Exception:
                    return str(pair)
            new_pairs=a_onko_pairs[len(b_onko_pairs):]
            rows.append({
                "severity":"ACK","kind":"CONSECUTIVE_ONKO","date":"; ".join(_fmt_onko_pair(x) for x in new_pairs),
                "before":str(len(b_onko_pairs)),"after":str(len(a_onko_pairs)),
                "explanation":"Swapas sukuria dvi Onko RO 9 val. dienas iš eilės. SYSTEM generatorius taip planuoti negali, tačiau abipusiu savanorišku apsikeitimu tai leidžiama, jei abu rezidentai aiškiai sutinka ir nepažeidžiamos tikros ABSOLUTE HARD poilsio / persidengimo taisyklės."
            })
        bpost=int(b.get("worked_after_two_doubles",0) or 0); apost=int(a.get("worked_after_two_doubles",0) or 0)
        if apost>bpost:
            rows.append({
                "severity":"ACK","kind":"POST_DOUBLE_RECOVERY","date":"po 2 dvigubų",
                "before":str(bpost),"after":str(apost),
                "explanation":"Po dviejų dvigubų dienų atsiranda dar viena darbo diena. Generatorius to vengia / draudžia, bet savanoriškame swape rezidentas gali sąmoningai sutikti."
            })
        brh=int(b.get("resident_hard_losses",0) or 0); arh=int(a.get("resident_hard_losses",0) or 0)
        if arh>brh:
            rows.append({
                "severity":"ACK","kind":"RESIDENT_HARD_SELF_OVERRIDE","date":"pageidavimas",
                "before":str(brh),"after":str(arh),
                "explanation":"Šiuo savanorišku swapu pats rezidentas sutinka dirbti per savo anksčiau pateiktą RESIDENT HARD „Negaliu dirbti“. Originalus pageidavimas istorijoje lieka, ACTUAL satisfaction perskaičiuojamas."
            })
        out[initials]=rows
    return out




def effective_actual_assignments(assignments: Dict[int,str], backup_assignments: Optional[List[dict]] = None) -> Dict[int,str]:
    """Return who actually worked each normal slot.

    ACTUAL normal swaps/operator repairs are already represented by ``assignments``.
    A backup row changes real-work ownership only after the cover is marked completed;
    planned or merely activated standby never changes fairness exposure.
    """
    out={int(k):str(v) for k,v in (assignments or {}).items() if v}
    for row in (backup_assignments or []):
        if not row.get("completed_at"):
            continue
        try:
            sid=int(row.get("covered_slot"))
        except Exception:
            continue
        coverer=str(row.get("actual_backup") or row.get("planned_backup") or "").strip()
        if coverer:
            out[sid]=coverer
    return out


def calculate_live_fairness_snapshot(
    year: int,
    month: int,
    assignments: Dict[int,str],
    people_initials: Optional[List[str]] = None,
    backup_assignments: Optional[List[dict]] = None,
) -> dict:
    """Current-month fairness calculated from real/effective work only.

    This is intentionally descriptive, not prescriptive: the returned ACTUAL metrics
    never feed a future solve. It is safe for manual overrides and accepted swaps to
    produce spreads wider than the SYSTEM water-fill corridor; the widening is shown
    here rather than blocked or converted into a future-month debt.
    """
    eff=effective_actual_assignments(assignments,backup_assignments)
    slots={s.idx:s for s in make_slots(year,month)}
    ids=list(people_initials or [])
    if not ids:
        ids=sorted({str(v) for v in eff.values() if v})
    # Preserve supplied cohort order while still showing any unexpected identity.
    seen=set(ids)
    for who in eff.values():
        if who and who not in seen:
            ids.append(who); seen.add(who)

    pdata={}
    for ini in ids:
        pslots=[slots[sid] for sid,who in eff.items() if who==ini and sid in slots]
        by_day={}
        for sl in pslots:
            by_day.setdefault(sl.day,[]).append(sl)
        rot={cat:0 for cat in ROTATION_CATEGORIES}
        for sl in pslots:
            cat=rotation_category(sl)
            if cat in rot:
                rot[cat]+=1
        pdata[ini]={
            "assignment_count":len(pslots),
            "workload":round(sum(float(sl.workload2)/2.0 for sl in pslots),1),
            "weekend_assignments":sum(1 for sl in pslots if sl.weekday>=5),
            "saturday_assignments":sum(1 for sl in pslots if sl.weekday==5),
            "sunday_assignments":sum(1 for sl in pslots if sl.weekday==6),
            "friday_assignments":sum(1 for sl in pslots if sl.weekday==4),
            "doubles":sum(1 for ds in by_day.values() if len(ds)==2),
            "weekday_days":sum(1 for d in by_day if date(year,month,d).weekday()<5),
            "distinct_work_days":len(by_day),
            "rotation_counts":rot,
            "distinct_rotations":sum(1 for v in rot.values() if v>0),
        }

    def _spread(vals):
        vals=list(vals)
        return (max(vals)-min(vals)) if vals else 0
    def _component(spread,allow_one=False):
        excess=max(0.0,float(spread)-(1.0 if allow_one else 0.0))
        return max(0.0,100.0-3.0*excess)

    weekend_spread=_spread(d["weekend_assignments"] for d in pdata.values())
    saturday_spread=_spread(d["saturday_assignments"] for d in pdata.values())
    sunday_spread=_spread(d["sunday_assignments"] for d in pdata.values())
    friday_spread=_spread(d["friday_assignments"] for d in pdata.values())
    double_spread=_spread(d["doubles"] for d in pdata.values())
    weekday_day_spread=_spread(d["weekday_days"] for d in pdata.values())
    rotation_spreads={
        cat:_spread(d["rotation_counts"].get(cat,0) for d in pdata.values())
        for cat in ROTATION_CATEGORIES
    }
    post_score=float(np.mean([_component(v,allow_one=True) for v in rotation_spreads.values()])) if rotation_spreads else 100.0
    score=(
        0.50*post_score
        +0.075*_component(saturday_spread)
        +0.075*_component(sunday_spread)
        +0.10*_component(friday_spread)
        +0.10*_component(double_spread,allow_one=True)
        +0.15*_component(weekday_day_spread,allow_one=True)
    )
    completed=sum(1 for r in (backup_assignments or []) if r.get("completed_at"))
    return {
        "people":pdata,
        "effective_assignments":eff,
        "global":{
            "monthly_fairness_score":round(float(score),1),
            "monthly_post_fairness_score":round(float(post_score),1),
            "weekend_monthly_spread":int(weekend_spread),
            "saturday_monthly_spread":int(saturday_spread),
            "sunday_monthly_spread":int(sunday_spread),
            "friday_monthly_spread":int(friday_spread),
            "double_monthly_spread":int(double_spread),
            "weekday_day_monthly_spread":int(weekday_day_spread),
            "rotation_monthly_spreads":{k:int(v) for k,v in rotation_spreads.items()},
            "rotation_monthly_imbalance":int(sum(rotation_spreads.values())),
            "completed_cover_transfers":int(completed),
            "future_catchup_enabled":False,
            "ledger_policy":"LIVE_ACTUAL_AUDIT_ONLY",
        },
    }


def _swap_hard_rule_row(error: str) -> dict:
    """Classify a technical validator error into a stable operational HARD code."""
    e=str(error or "")
    low=e.lower()
    code="OTHER_OPERATIONAL_HARD"
    rule="Operational HARD rule"

    if "workload" in low and "exact target" in low:
        code="EXACT_MONTHLY_WORKLOAD"
        rule="Exact monthly workload"
    elif "odd onko count" in low:
        code="ONKO_EVEN_PARITY"
        rule="Onko even-pair parity"
    elif "onko coverage" in low:
        code="ONKO_COVERAGE"
        rule="Onko required coverage"
    elif "overlapping assignments" in low:
        code="OVERLAPPING_ASSIGNMENTS"
        rule="No overlapping assignments"
    elif "exceeds max hours/day" in low:
        code="MAX_HOURS_PER_DAY"
        rule="Maximum hours per day"
    elif "workdays/7d cap exceeded" in low:
        code="MAX_WORKDAYS_7D"
        rule="Maximum working days in rolling 7 days"
    elif "hours/7d cap exceeded" in low:
        code="MAX_HOURS_7D"
        rule="Maximum hours in rolling 7 days"
    elif "rest between days" in low:
        code="MIN_DAILY_REST"
        rule="Minimum daily rest"
    elif "mandatory post-duty rest" in low:
        code="POST_DUTY_REST"
        rule="Mandatory post-duty rest"
    elif "work during vacation" in low or "work during justified absence" in low:
        code="ABSOLUTE_UNAVAILABILITY"
        rule="Absolute unavailability"
    elif "blocked slot filled" in low:
        code="BLOCKED_SLOT"
        rule="Blocked/closed shift"
    elif "mandatory slot unfilled" in low:
        code="MANDATORY_COVERAGE"
        rule="Mandatory service coverage"
    elif "no hard-available non-overlapping backup resident" in low:
        code="MANDATORY_BACKUP_AVAILABILITY"
        rule="Required backup availability"
    elif "weekend" in low and "cap exceeded" in low:
        code="WEEKEND_CAP"
        rule="Weekend assignment cap"
    elif "consecutive onko" in low:
        code="CONSECUTIVE_ONKO_GENERATION"
        rule="Consecutive Onko generation rule"
    elif "gap " in low or "gap-" in low:
        code="GENERATOR_GAP_FAIRNESS"
        rule="Generator-only optional-gap fairness"
    elif "friday structural" in low:
        code="GENERATOR_FRIDAY_FAIRNESS"
        rule="Generator-only Friday fairness"

    return {"severity":"BLOCK","code":code,"rule":rule,"details":e}


def _swap_ack_fingerprint(rows: List[dict]) -> str:
    raw="|".join(
        f"{r.get('severity')}::{r.get('kind')}::{r.get('date')}::{r.get('after')}::{r.get('explanation')}"
        for r in rows
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] if rows else ""


def preview_swap(year: int, month: int, people: List[Person], result: SolveResult,
                 slot_a_idx: int, slot_b_idx: int,
                 backup_assignments: Optional[List[dict]] = None) -> Tuple[bool, str, Optional[Dict[str, dict]], Dict[str,str]]:
    """Dry-run a bilateral voluntary swap using the V2.5.55 reality guardrails.

    HARD blockers for a swap are deliberately narrow: ABSOLUTE-HARD/justified
    absence, overlapping assignments, >12h/day, <11h daily rest, >6 workdays in
    any rolling 7, >60h in any rolling 7, mandatory post-duty rest and operational
    backup/coverage feasibility and even Onko pairing. Monthly workload CREDIT is
    frozen at publication and is never recalculated from ACTUAL placement. Generator-only
    fatigue shaping, the 48h generation ceiling, consecutive
    Onko, weekend uniqueness, preference, workplace water-fill, post spread, modality
    diversity and educational exposure are NOT blockers; affected residents may
    voluntarily create an uneven ACTUAL post matrix by bilateral acceptance. Onko
    parity remains a separate ACTUAL invariant; target/workload CREDIT does not move.
    """
    # V2.5.81: a stored/published CURRENT may have result.ok=False only because
    # it was live-revalidated against newer SYSTEM-generation fairness rules
    # (e.g. Friday/gap water-fill introduced after publication). That must never
    # block an ACTUAL voluntary swap. Revalidate the existing CURRENT using only
    # ACTUAL operational/safety rules before deciding whether a usable base exists.
    if not result.ok:
        frozen_people=people_from_request_snapshot(result.request_snapshot)
        baseline_stats=validate_schedule(
            year,month,people,make_slots(year,month),result.assignments,result.targets,
            satisfaction_people=(frozen_people or people),
            backup_assignments=(backup_assignments if backup_assignments is not None else result.backup_snapshot),
            validation_mode="voluntary_swap_baseline",
        )
        if baseline_stats["global"]["hard_errors"]:
            block_rows=[_swap_hard_rule_row(e) for e in baseline_stats["global"].get("errors",[])]
            baseline_stats["global"]["swap_hard_block_rows"]=block_rows
            return False, (
                "CURRENT ACTUAL already contains an operational HARD violation before this swap: "
                + (block_rows[0]["details"] if block_rows else "unknown HARD rule")
            ), baseline_stats, {}
    if slot_a_idx == slot_b_idx:
        return False, "Pasirinktos tos pačios pamainos.", None, {}
    if slot_a_idx not in result.assignments or slot_b_idx not in result.assignments:
        return False, "Abi pasirinktos pamainos turi būti užpildytos.", None, {}
    a_person=result.assignments[slot_a_idx]; b_person=result.assignments[slot_b_idx]
    if a_person==b_person:
        return False, "Abi pamainos priklauso tam pačiam žmogui.", None, {}
    new_assign=dict(result.assignments)
    new_assign[slot_a_idx],new_assign[slot_b_idx]=b_person,a_person
    frozen_people=people_from_request_snapshot(result.request_snapshot)
    stats=validate_schedule(
        year,month,people,make_slots(year,month),new_assign,result.targets,
        satisfaction_people=(frozen_people or people),
        backup_assignments=(backup_assignments if backup_assignments is not None else result.backup_snapshot),
        validation_mode="voluntary_swap",
    )
    if stats["global"]["hard_errors"]:
        rows=[_swap_hard_rule_row(e) for e in stats["global"].get("errors",[])]
        # Defensive invariant: generator-only fairness must never be an ACTUAL
        # swap blocker. If a future validator accidentally emits one in voluntary
        # mode, discard it from the blocking set.
        generator_only={"GENERATOR_GAP_FAIRNESS","GENERATOR_FRIDAY_FAIRNESS","CONSECUTIVE_ONKO_GENERATION"}
        real_rows=[r for r in rows if r.get("code") not in generator_only]
        stats["global"]["swap_hard_block_rows"]=real_rows
        if real_rows:
            return False, real_rows[0]["details"], stats, {}
        # No true ACTUAL blocker remained. Generator-only fairness must not leave
        # a stale non-zero hard_errors counter on an otherwise valid voluntary swap.
        stats["global"]["errors"]=[]
        stats["global"]["hard_errors"]=0

    warnings=_swap_warning_rows(year,month,people,result,stats,(a_person,b_person))
    ack_needed={who:_swap_ack_fingerprint(rows) for who,rows in warnings.items() if rows}
    stats["global"]["swap_warning_rows"]=warnings
    stats["global"]["swap_ack_fingerprints"]=dict(ack_needed)
    stats["global"]["swap_policy"]="V2585_ACTUAL_PLACEMENT_FAIRNESS_FREE; FROZEN_SYSTEM_WORKLOAD_CREDIT; ONKO_PARITY_STILL_HARD"
    return True,"SWAP PREVIEW OK",stats,ack_needed


def attempt_swap(year: int, month: int, people: List[Person], result: SolveResult,
                 slot_a_idx: int, slot_b_idx: int,
                 backup_assignments: Optional[List[dict]] = None,
                 weekly_hours_override_caps: Optional[Dict[str,float]] = None,
                 acknowledged_fingerprints: Optional[Dict[str,str]] = None) -> Tuple[bool, str, Optional[Dict[str, dict]]]:
    # V2.5.81: preview_swap performs an ACTUAL operational base check. Do not
    # reject merely because a legacy published payload failed a newer generator-
    # fairness revalidation.
    if slot_a_idx == slot_b_idx:
        return False, "Pasirinktos tos pačios pamainos.", None
    if slot_a_idx not in result.assignments or slot_b_idx not in result.assignments:
        return False, "Abi pasirinktos pamainos turi būti užpildytos.", None

    ok,msg,stats,needed=preview_swap(
        year,month,people,result,slot_a_idx,slot_b_idx,backup_assignments=backup_assignments
    )
    if not ok:
        return False,msg,stats
    acked={str(k):str(v) for k,v in (acknowledged_fingerprints or {}).items()}
    missing=[who for who,fp in needed.items() if acked.get(who)!=fp]
    if missing:
        return False,f"SWAP REJECTED — trūksta atnaujinto pasekmių patvirtinimo: {', '.join(missing)}",stats

    a_person=result.assignments[slot_a_idx]; b_person=result.assignments[slot_b_idx]
    new_assign=dict(result.assignments)
    new_assign[slot_a_idx],new_assign[slot_b_idx]=b_person,a_person
    stats["global"]["voluntary_swap_actual"]=True
    stats["global"]["swap_ack_fingerprints"]={k:v for k,v in acked.items() if k in (a_person,b_person)}
    result.assignments=new_assign
    result.stats=stats
    return True,"SWAP APPROVED",stats


def revalidate_loaded_result(
    year: int, month: int, people: List[Person], result: SolveResult,
    backup_assignments: Optional[List[dict]] = None,
    validation_mode: Optional[str] = None,
) -> SolveResult:
    """Recompute a stored schedule while preserving its ORIGINAL request snapshot.

    V2.5.49 deliberately prevents later preference edits from rewriting historical
    satisfaction. If a frozen request snapshot exists, it is the source of truth for
    request/fairness scoring; current DB people remain the fallback for legacy payloads.
    """
    frozen_people=people_from_request_snapshot(result.request_snapshot)
    source_people=frozen_people or people
    normalized_people,_audit=normalize_preferences_against_engine(source_people,year,month)
    current_targets=calculate_targets(year,month,normalized_people)
    slots=make_slots(year,month)
    source_global=(result.stats or {}).get("global",{})
    stored_weekly_override_caps={str(k):float(v) for k,v in (source_global.get("swap_weekly_hours_override_caps") or {}).items()}
    stored_voluntary_swap_actual=bool(source_global.get("voluntary_swap_actual",False))
    effective_validation_mode=(
        str(validation_mode)
        if validation_mode
        else ("voluntary_swap_actual" if stored_voluntary_swap_actual else "generation")
    )
    stats=validate_schedule(
        year,month,normalized_people,slots,result.assignments,current_targets,
        satisfaction_people=(frozen_people or normalized_people),
        backup_assignments=(backup_assignments if backup_assignments is not None else result.backup_snapshot),
        weekly_hours_override_caps=stored_weekly_override_caps,
        validation_mode=effective_validation_mode
    )
    for key in (
        "solve_stage","fairness_guardrails","fairness_guardrails_established",
        "gap_plan","planned_gap_count","local_repair_accepted_swaps","local_repair_attempts",
        "quality_repair_accepted_swaps","post_ceiling_rescue_attempted","post_ceiling_rescue_succeeded",
        "solver_worst_raw_post_spread","solver_worst_normalized_post_spread",
        "solver_min_exact_preference_ratio","solver_active_exact_preference_residents",
        "solver_total_exact_preference_requests","resident_hard_total_requests",
        "resident_hard_min_total_found","resident_hard_minimum_proven",
        "resident_hard_current_max_lock","resident_hard_cumulative_spread_lock",
        "hard_classification","preference_normalization","preference_normalization_count",
        "weekly_load_waterfill","swap_weekly_hours_override_caps","swap_weekly_hours_override_audit",
        "voluntary_swap_actual","swap_ack_fingerprints","swap_warning_rows","swap_policy","swap_ack_audit"
    ):
        if key in source_global:
            stats["global"][key]=source_global[key]
    stats["global"]["live_revalidated"]=True
    stats["global"]["stored_stats_replaced"]=True
    ok=stats["global"]["hard_errors"]==0
    return SolveResult(
        ok=ok,
        message=("LIVE REVALIDATION — PASSED" if ok else "LIVE REVALIDATION — CURRENT ENGINE VIOLATIONS"),
        assignments=dict(result.assignments),
        targets=current_targets,
        stats=stats,
        objective_value=result.objective_value,
        request_snapshot=result.request_snapshot,
        backup_snapshot=result.backup_snapshot,
    )


def serialize_result(result: SolveResult) -> dict:
    return {
        "engine_stats_version": "V2.5.77",
        "ok": result.ok,
        "message": result.message,
        "assignments": {str(k): v for k, v in result.assignments.items()},
        "targets": result.targets,
        "stats": result.stats,
        "objective_value": result.objective_value,
        "request_snapshot": result.request_snapshot,
        "backup_snapshot": result.backup_snapshot,
    }


def deserialize_result(payload: dict) -> SolveResult:
    return SolveResult(
        ok=bool(payload.get("ok")),
        message=payload.get("message", ""),
        assignments={int(k): v for k, v in payload.get("assignments", {}).items()},
        targets={str(k): int(v) for k, v in payload.get("targets", {}).items()},
        stats=payload.get("stats", {}),
        objective_value=payload.get("objective_value"),
        request_snapshot=payload.get("request_snapshot"),
        backup_snapshot=payload.get("backup_snapshot"),
    )
