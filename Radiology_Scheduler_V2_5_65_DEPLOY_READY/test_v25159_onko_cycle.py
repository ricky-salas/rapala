from pathlib import Path
from collections import Counter
import ast
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

assert se.ENGINE_API_VERSION=='2.5.159'
assert 'APP_VERSION = "2.5.159 ONKO CYCLE LEDGER"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.159"' in APP
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.159"}' in APP

# App/engine import contract.
tree=ast.parse(APP)
engine_names=[]
for node in ast.walk(tree):
    if isinstance(node,ast.ImportFrom) and node.module=='scheduler_engine':
        engine_names.extend(a.name for a in node.names)
missing=[n for n in engine_names if not hasattr(se,n)]
assert not missing, missing

# Authoritative September seed supplied by SP/warden.
SEPTEMBER_ONKO={'SE','KE','MR','ŠR','GB','GD','DU','SA','MŽ','GE','PV'}
for ini in SEPTEMBER_ONKO:
    assert f'"{ini}": 2' in APP

# The five people still waiting at the start of October.
WAITING={'MG','SŠ','VL','SP','SN'}
assert WAITING == {p['initials'] for p in se.DEFAULT_PEOPLE} - SEPTEMBER_ONKO

people=[]
for base in se.DEFAULT_PEOPLE:
    prior={cat:0 for cat in se.ROTATION_CATEGORIES}
    prior['Onko/TBL']=2 if base['initials'] in SEPTEMBER_ONKO else 0
    people.append(se.Person(
        initials=base['initials'], name=base['name'],
        target_adjustment=base.get('target_adjustment',0),
        prior_rotation_counts=prior,
    ))

r=se.solve_schedule(2026,10,people,time_limit=90)
assert r.ok, r.message
assert not ((r.stats or {}).get('global',{}).get('errors') or [])

onko=[s for s in se.make_slots(2026,10) if se.is_onko_slot(s) and not s.blocked]
counts=Counter(r.assignments[s.idx] for s in onko if s.idx in r.assignments)
assert sum(counts.values())==22
assert all(counts.get(ini,0)==2 for ini in WAITING), counts
assert all(v in (0,2) for v in counts.values()), counts

prior=r.stats['global']['onko_cycle_prior_counts']
month=r.stats['global']['onko_cycle_month_counts']
cumulative=r.stats['global']['onko_cycle_cumulative_counts']
assert all(prior[ini]==0 for ini in WAITING)
assert all(prior[ini]==2 for ini in SEPTEMBER_ONKO)
assert all(cumulative[ini]>=2 for ini in WAITING)
assert max(cumulative.values())-min(cumulative.values())<=2

# Suvestinė exposes the ledger explicitly.
assert 'Onko iki mėnesio' in APP
assert 'Onko šį mėnesį' in APP
assert 'Onko ciklas iš viso' in APP
assert 'historical_onko_cycle_counts_before' in APP

print('PASS V2.5.159 — Onko cumulative cycle + Suvestinė ledger')
print('September cohort:',sorted(SEPTEMBER_ONKO))
print('October first-priority waiting cohort:',sorted(WAITING))
print('October Onko counts:',dict(counts))
print('Cumulative after October:',cumulative)
