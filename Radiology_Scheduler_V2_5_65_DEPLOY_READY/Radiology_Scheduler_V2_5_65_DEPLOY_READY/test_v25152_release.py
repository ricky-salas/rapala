from pathlib import Path
import time

import scheduler_engine as se

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "scheduler_engine.py").read_text(encoding="utf-8")
P = se.Person


def current_like_october_people():
    """Deterministic fixture reconstructed from the active Oct-2026 request pattern.

    It deliberately includes the two edge cases that motivated V2.5.152:
    * PV has a preferred-work request on day 20 that conflicts with FULL HARD unavailability.
    * MR and VL both want the only Oct-4 weekend duty; MR has the better submission rank.
    """
    return [
        P("DU", "Dulkė Sofija Ana", unavailable={11}, unavailable_am={12}, unavailable_pm={2}, preference_priority_rank=3, preference_priority_points=14, prior_consecutive_weekend_streak=1),
        P("GB", "Grumblys Justinas", unavailable={2,3,4}, unavailable_pm={9,16,23,30}, soft_free={2,3,4}, shift_length_preference=3, holiday_preference=1, preference_priority_rank=12, preference_priority_points=5),
        P("GD", "Giedrimas Deivydas"),
        P("GE", "Gertas Ernestas", soft_free={8,9,22,23}, preferred={7,21}, preference_priority_rank=5, preference_priority_points=12),
        P("KE", "Khatskeleva Elena", unavailable={4}, soft_free={5,24,31}, preference_priority_rank=2, preference_priority_points=15, prior_last_day_onko=True),
        P("MG", "Maleckaitė Gabrielė", unavailable={1,2,3,4,5,6}, preference_priority_rank=7, preference_priority_points=10, prior_consecutive_weekend_streak=1),
        P("MR", "Montvilaitė Reda", unavailable_am={3,10,17,24,31}, soft_free={2,9,16,23,30}, soft_free_pm={1,8,15,22,29}, preferred={5,6,7,12,13,14,19,20,21,26,27,28}, preferred_am={1,8,15,22,29}, preferred_pm={4}, preference_priority_rank=11, preference_priority_points=6, prior_consecutive_weekend_streak=1),
        P("MŽ", "Mažonavičius Ignas", unavailable={31}, soft_free={9}, soft_free_pm={8}, shift_length_preference=2, preference_priority_rank=14, preference_priority_points=3),
        P(
            "PV", "Pileckienė Aistė",
            unavailable={17,18,19,20},
            preferred={1,6,7,8,13,14,15,20,21,22,27,28,29},
            shift_length_preference=3, holiday_preference=-1,
            preference_priority_rank=10, preference_priority_points=7,
            request_items=[
                {"id":"hard20", "kind":"resident_hard", "tier":"RESIDENT_HARD", "day":20, "block":"FULL", "source":"monthly", "included_in_score":True},
                {"id":"pref20", "kind":"preferred", "tier":"SOFT2_POSITIVE_PLACEMENT", "day":20, "block":"FULL", "source":"recurring", "included_in_score":True},
            ],
        ),
        P("SA", "Sveboda Arminas", shift_length_preference=3),
        P("SE", "Stanišauskytė Eglė", unavailable={3,4,10,11}, unavailable_pm={2}, preference_priority_rank=4, preference_priority_points=13),
        P("SN", "Stankevičiūtė Vytautė", unavailable={5,6,15,29}, unavailable_pm={14,28}, preference_priority_rank=8, preference_priority_points=9),
        P("SP", "Steponavičiūtė Rosita", unavailable={10,11}, target_adjustment=-2, shift_length_preference=2, preference_priority_rank=6, preference_priority_points=11),
        P("ŠR", "Šalaševičius Rapolas", unavailable_pm={1,6,8,13,15,20,22,27,29}, shift_length_preference=3, preference_priority_rank=1, preference_priority_points=16),
        P("SŠ", "Stašinskas Kipras", unavailable={9,10,16,17}, preference_priority_rank=9, preference_priority_points=8),
        P("VL", "Volkovskaja Laura", unavailable={2,3,8,9,10,13,22,23,27,30}, preferred={1,4,5,7,14}, shift_length_preference=2, holiday_preference=1, preference_priority_rank=13, preference_priority_points=4),
    ]


def run():
    # Release/version contract.
    assert se.ENGINE_API_VERSION == "2.5.152"
    assert 'APP_VERSION = "2.5.152 STRICT FAIRNESS + WISH AUDIT"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.152"' in APP
    assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.152"}' in APP

    # 1) HARD-vs-SOFT normalization: preserve raw intent for audit, deactivate it for scoring.
    p = P(
        "PV", "Synthetic PV", unavailable={20}, preferred={20},
        request_items=[
            {"id":"hard20", "kind":"resident_hard", "tier":"RESIDENT_HARD", "day":20, "block":"FULL", "source":"monthly", "included_in_score":True},
            {"id":"pref20", "kind":"preferred", "tier":"SOFT2_POSITIVE_PLACEMENT", "day":20, "block":"FULL", "source":"recurring", "included_in_score":True},
        ],
    )
    normalized, audit = se.normalize_preferences_against_engine([p], 2026, 10)
    np = normalized[0]
    assert 20 not in np.preferred
    pref = next(x for x in np.request_items if x.get("id") == "pref20")
    assert pref["included_in_score"] is False
    assert pref["normalization_status"] == "INACTIVE"
    assert pref["normalization_reason"] == "CONFLICTS_WITH_HARD_UNAVAILABILITY_NOT_SCORED"
    assert audit
    snap = se.serialize_people_request_snapshot(normalized)
    assert snap["schema"] == "V25152_NORMALIZED_REQUEST_SNAPSHOT"
    assert next(x for x in snap["people"][0]["request_items"] if x.get("id") == "pref20")["included_in_score"] is False

    # 2) Relaxation is proof-gated. A timeout/no-incumbent triggers a retry in the SAME corridor;
    # widening is only reached after solver status 2 (proven infeasible).
    assert 'strict_work_pattern_same_corridor_retry' in ENGINE
    assert 'same_structural_frontier_retry' in ENGINE
    assert 'if pattern is None and int(_diag.get("status",99))!=2:' in ENGINE
    assert 'TIGHTEST_PROVEN_FEASIBLE_HARD_ELIGIBILITY_V25152' in ENGINE
    assert 'friday_entitlement_max_deviation' in ENGINE

    # 3) UI/validator explanation distinguishes an occupied matching shift from a missing shift.
    assert 'PREFERRED_CONFLICT_ASSIGNED_TO_OTHER' in ENGINE
    assert 'NO_ACTIVE_SHIFT_IN_BLOCK' in ENGINE
    assert 'competing_assignments' in ENGINE
    assert 'PREFERRED_CONFLICT_ASSIGNED_TO_OTHER' in APP

    # 4) End-to-end current-like October regression.
    people = current_like_october_people()
    started = time.time()
    result = se.solve_schedule(2026, 10, people, time_limit=90)
    elapsed = time.time() - started
    assert result.ok, result.message
    g = result.stats["global"]
    assert int(g.get("hard_errors", 999)) == 0
    assert int(g.get("resident_hard_total_losses", 999)) == 0
    assert bool(g.get("friday_structural_gate_passed")) is True
    assert int(g.get("friday_entitlement_relaxation_radius", 99)) == 0
    assert int((g.get("critical_structural_spreads") or {}).get("FRIDAYS", 99)) == 0

    # PV's impossible positive wish is audit-only and no longer harms the denominator.
    pv20 = next(x for x in result.stats["people"]["PV"]["request_detail_rows"] if x.get("request_id") == "pref20")
    assert pv20["included_in_score"] is False
    assert pv20["normalization_status"] == "INACTIVE"

    # The single Oct-4 FULL weekend shift is a genuine SOFT2 conflict. Max-count is locked first;
    # then submission rank breaks the tie in MR's favour (MR rank 11 vs VL rank 13).
    mr4 = [x for x in result.stats["people"]["MR"]["request_detail_rows"] if x.get("kind") == "preferred" and int(x.get("day",0)) == 4]
    vl4 = [x for x in result.stats["people"]["VL"]["request_detail_rows"] if x.get("kind") == "preferred" and int(x.get("day",0)) == 4]
    assert mr4 and mr4[0]["fulfilled"] is True
    assert vl4 and vl4[0]["fulfilled"] is False
    assert vl4[0]["unmet_reason_code"] == "PREFERRED_CONFLICT_ASSIGNED_TO_OTHER"
    assert any(x.get("assigned_to") == "MR" for x in (vl4[0].get("competing_assignments") or []))

    # Revalidation must preserve the same validity and normalization semantics.
    checked = se.revalidate_loaded_result(2026, 10, people, result, backup_assignments=[])
    assert checked.ok
    assert int(checked.stats["global"].get("hard_errors",999)) == 0
    assert bool(checked.stats["global"].get("friday_structural_gate_passed")) is True
    pv20_checked = next(x for x in checked.stats["people"]["PV"]["request_detail_rows"] if x.get("request_id") == "pref20")
    assert pv20_checked["included_in_score"] is False

    print(f"V2.5.152 strict fairness + wish audit PASS ({elapsed:.1f}s integration solve)")


if __name__ == "__main__":
    run()
