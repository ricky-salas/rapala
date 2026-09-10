from datetime import date
from pathlib import Path

import numpy as np
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENGINE=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')


def run():
    # Release contract: app and optimizer move together.
    assert se.ENGINE_API_VERSION == '2.5.153'
    assert 'APP_VERSION = "2.5.154 SURVEY ALL MODES"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.153"' in APP
    assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.153"}' in APP

    # Regression 1: bounded water-fill respects a hard capacity bottleneck.
    # 100 Friday assignments, one resident can accept only 2, peers can accept 10.
    caps=[10]*16
    caps[10]=2
    lo,hi=se._bounded_waterfill_bounds(100,caps)
    assert lo[10] == 2 and hi[10] == 2
    assert all(lo[i] <= hi[i] <= caps[i] for i in range(16))
    assert sum(lo) <= 100 <= sum(hi)

    # Regression 2: HARD Friday availability is converted into actual block capacity,
    # rather than a universal cohort floor. October 2026 has five Fridays; with four
    # full Fridays blocked, only the remaining AM+PM blocks are mathematically usable.
    slots=se.make_slots(2026,10)
    friday_days=[d for d in range(1,32) if date(2026,10,d).weekday()==4]
    assert friday_days == [2,9,16,23,30]
    person=se.Person(initials='T1',name='Synthetic test resident',unavailable={2,9,23,30})
    cap=se._friday_assignment_capacity(person,2026,10,slots,set())
    assert cap == 2, cap

    # Regression 3: compact two-phase builder accepts the legacy named-constraint
    # calling convention used by account-mode refinement and solves a tiny MILP.
    mb=se._V2564FastMB()
    x=mb.var(lb=0,ub=1,integer=True,cost=-1)
    mb.constraint({x:1},0,1,'named_lock')
    res=mb.solve(seconds=2)
    assert int(getattr(res,'status',9)) == 0
    assert int(round(float(res.x[x]))) == 1

    # Regression 4: post-label gate compares weekday/post-category SPS spreads,
    # not weekend-inclusive SPS RO burden. Date burden stays in its own phase-1 gate.
    assert '_post_critical=max(int(rotation_spreads.get("SPS RO",0)),int(rotation_spreads.get("SPS UG",0)))' in ENGINE
    assert '_weekend_structural=max(int(critical_spreads.get("SATURDAYS",0)),int(critical_spreads.get("SUNDAYS",0)))' in ENGINE
    assert '_friday_entitlement_dev=int(critical_spreads.get("FRIDAYS",0))' in ENGINE
    assert 'TIGHTEST_PROVEN_FEASIBLE_HARD_ELIGIBILITY_V25152' in ENGINE

    # UI now states the actual selected month / submissions / draft existence.
    assert 'pateikė {_submitted_count}/{len(DEFAULT_PEOPLE)} · juodraštis:' in APP
    assert '("yra" if state.get("has_draft") else "nėra")' in APP

    print('V2.5.151 hard-aware Friday behavior retained on V2.5.153 PASS')


if __name__=='__main__':
    run()
