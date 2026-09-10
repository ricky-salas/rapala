from pathlib import Path
from collections import Counter
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

assert se.ENGINE_API_VERSION=='2.5.157'
assert 'APP_VERSION = "2.5.157 ADMIN STATIONS + NO BLOCK"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.157"' in APP
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.157"}' in APP

slots=se.make_slots(2026,10)
visible=[s for s in slots if se.slot_visible_in_schedule(s,2026,10)]
assert all(not s.blocked for s in visible)
assert not any(s.blocked and se.slot_visible_in_schedule(s,2026,10) for s in slots)

# Skopijos: one AM row Monday-Thursday, hard-covered, from Oct 1.
sk=[s for s in slots if s.department=='Skopijos' and not s.blocked]
assert sk and all(s.block=='AM' and s.weekday in {0,1,2,3} and s.mandatory for s in sk)
assert any(s.day==13 for s in sk)
assert not any(s.weekday==4 for s in sk)

# MUST admin tier.
assert all(s.mandatory for s in slots if not s.blocked and s.department.startswith('CENTRO RO'))
assert all(s.mandatory for s in slots if not s.blocked and se.rotation_category(s)=='Onko/TBL')
assert all(s.mandatory for s in slots if not s.blocked and s.department.startswith('SPS RO'))
assert all(s.mandatory for s in slots if not s.blocked and s.department.startswith('Centro UG 120') and s.block=='AM')
assert all(se.admin_coverage_priority_tier(s,2026,10)==0 for s in sk)

# Second tier.
second=[s for s in slots if not s.blocked and (
    (s.department.startswith('Vaikų UG') and s.block=='AM') or
    ((s.department.startswith('ADC 144') or s.department.startswith('145') or s.department.startswith('ADC 145')) and s.block=='AM') or
    (s.department.startswith('Centro UG 120') and s.block=='PM')
)]
assert second and all(not s.mandatory and se.admin_coverage_priority_tier(s,2026,10)==1 for s in second)

# Last tier + retired SPS UG PM.
last=[s for s in slots if not s.blocked and (
    ((s.department.startswith('ADC 144') or s.department.startswith('145') or s.department.startswith('ADC 145')) and s.block=='PM') or
    (s.department.startswith('SPS UG') and s.block=='AM')
)]
assert last and all(not s.mandatory and se.admin_coverage_priority_tier(s,2026,10)==2 for s in last)
sps_pm=[s for s in slots if s.department.startswith('SPS UG') and s.block=='PM']
assert sps_pm and all(s.blocked and not se.slot_visible_in_schedule(s,2026,10) for s in sps_pm)

# Mammography remains only as an internal tombstone from Oct onward.
mammo=[s for s in slots if s.department.startswith('Mamografijos')]
assert mammo and all(s.blocked and not se.slot_visible_in_schedule(s,2026,10) for s in mammo)

# Default October gap plan must sacrifice LAST tier before SECOND tier.
people=[se.Person(initials=p['initials'],name=p['name'],target_adjustment=p.get('target_adjustment',0)) for p in se.DEFAULT_PEOPLE]
targets=se.calculate_targets(2026,10,people)
_,meta,errs=se.plan_distributed_gaps(2026,10,people,slots,targets)
assert not errs, errs
fixed=se._v2564_choose_fixed_gaps(2026,10,slots,meta,seconds=10)
assert fixed is not None
assert all(se.admin_coverage_priority_tier(slots[sid],2026,10)==2 for sid in fixed), [
    (slots[sid].day,slots[sid].department,slots[sid].block,se.admin_coverage_priority_tier(slots[sid],2026,10)) for sid in fixed
]

# Full generation regression.
r=se.solve_schedule(2026,10,people,time_limit=90)
assert r.ok, r.message
must_unfilled=[s for s in slots if s.mandatory and not s.blocked and s.idx not in r.assignments]
assert not must_unfilled, [(s.day,s.department,s.block) for s in must_unfilled]
second_unfilled=[s for s in second if s.idx not in r.assignments]
assert not second_unfilled, [(s.day,s.department,s.block) for s in second_unfilled]
actual_gaps=Counter((se.admin_coverage_priority_tier(s,2026,10),se.rotation_category(s),s.block)
                    for s in slots if not s.blocked and not s.mandatory and s.idx not in r.assignments)
assert actual_gaps and all(k[0]==2 for k in actual_gaps), actual_gaps

# Human-facing schedule has no BLOCK sentinel and carries room exception text.
grid_src=APP[APP.index('def schedule_grid('):APP.index('def style_schedule(')]
assert '"BLOCK" if s.blocked' not in grid_src
assert 'slot_department_text(y,m,s,grid=True)' in grid_src
assert '10-13 → KP 209' in APP
assert 'Konsultacinė poliklinika 209' in APP

print('PASS V2.5.157: admin stations, tiered coverage, Skopijos, no visible BLOCK')
print('October gaps:',dict(actual_gaps))
