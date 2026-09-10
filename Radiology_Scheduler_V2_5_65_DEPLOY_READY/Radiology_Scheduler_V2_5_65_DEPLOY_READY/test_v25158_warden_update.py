from pathlib import Path
from collections import Counter
import ast
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

assert se.ENGINE_API_VERSION=='2.5.158'
assert 'APP_VERSION = "2.5.158 WARDEN ONKO + SPS UG PM + GRID CLEANUP"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.158"' in APP
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.158"}' in APP

# Exact import contract without executing Streamlit UI.
tree=ast.parse(APP)
engine_names=[]
for node in ast.walk(tree):
    if isinstance(node,ast.ImportFrom) and node.module=='scheduler_engine':
        engine_names.extend(a.name for a in node.names)
missing=[n for n in engine_names if not hasattr(se,n)]
assert not missing, missing

slots=se.make_slots(2026,10)
visible=[s for s in slots if se.slot_visible_in_schedule(s,2026,10)]
assert visible and all(not s.blocked for s in visible)

# 1) Onko/TBL is one 08-17 FULL row, 1.5 shift-units, not AM+PM.
onko=[s for s in slots if se.is_onko_slot(s) and not s.blocked]
assert len(onko)==se.weekday_count(2026,10)==22
assert all(s.department=='Onkologinė/TBL' for s in onko)
assert all(s.block=='FULL' and s.workload2==3 and s.mandatory for s in onko)
assert all(se.scheduled_slot_clock(s)==(8.0,17.0) and se.scheduled_slot_hours(s)==9.0 for s in onko)
assert not any(s.department=='Onkologinė/TBL' and s.block in ('AM','PM') and not s.blocked for s in slots)

# 2) SPS UG 1035 PM is restored and visible. Until a PM tier is explicitly supplied,
# it stays in the same optional/last tier as SPS UG AM rather than being invented as MUST.
sps_pm=[s for s in slots if s.department=='SPS UG 1035kab' and s.block=='PM' and not s.blocked]
assert len(sps_pm)==22
assert all(se.slot_visible_in_schedule(s,2026,10) for s in sps_pm)
assert all(not s.mandatory and se.admin_coverage_priority_tier(s,2026,10)==2 for s in sps_pm)

# Existing weekend/holiday duty model remains HARD, as requested by user.
duties=[s for s in slots if s.department.startswith('SPS RO budėjimai') and not s.blocked]
assert duties and all(s.mandatory for s in duties)
assert se.rule_value('weekend_unique_required') is True

# 3) October Onko eligibility: residents with September Onko are excluded HARD.
people=[]
for idx,p in enumerate(se.DEFAULT_PEOPLE):
    people.append(se.Person(
        initials=p['initials'], name=p['name'], target_adjustment=p.get('target_adjustment',0),
        prior_month_onko_count=(2 if idx<5 else 0)
    ))
r=se.solve_schedule(2026,10,people,time_limit=90)
assert r.ok, r.message
assert not ((r.stats or {}).get('global',{}).get('errors') or [])
counts=Counter(r.assignments[s.idx] for s in onko if s.idx in r.assignments)
for p in people[:5]:
    assert counts.get(p.initials,0)==0, (p.initials,counts)
for p in people[5:]:
    assert counts.get(p.initials,0)==2, (p.initials,counts)
assert sum(counts.values())==22

# 4) Presentation cleanup: Centro UG rows are explicitly adjacent in ordering,
# night duty row is visible as a non-operational scaffold, and resident text is uniform white.
assert 'if s.startswith("Centro UG 120"): return (30' in APP
assert 'SPS RO naktiniai budėjimai [Naktis]' in APP
assert 'presentation scaffold only' in APP
assert 'color:#FFFFFF' in APP
assert 'schedule_pf' in APP and '"font_color":"#FFFFFF"' in APP

# No visible BLOCK sentinel in the schedule grid path.
grid_src=APP[APP.index('def schedule_grid('):APP.index('def style_schedule(')]
assert '"BLOCK"' not in grid_src and "'BLOCK'" not in grid_src

print('PASS V2.5.158 — Warden Onko/SPS UG PM/grid update')
print('Onko eligibility counts:',dict(counts))
print('SPS UG PM rows:',len(sps_pm),'| existing HARD duty rows:',len(duties))
