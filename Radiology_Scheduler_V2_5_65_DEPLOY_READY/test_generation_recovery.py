"""Regression coverage for immediate stale drafts and strict timeout recovery."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import scheduler_engine as se

app_text=Path(se.__file__).with_name('app.py').read_text()
assert se.ENGINE_API_VERSION=='2.5.175'
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.175"' in app_text
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.175"}' in app_text

p=se.Person('AA','A',unavailable={5},preferred={5,6},prior_weekend_count=4,
    prior_rotation_counts={'CENTRO RO':8,'Onko RO':2},
    request_items=[{'kind':'preferred','day':5,'block':'FULL'}])
prepared,_=se.prepare_generation_people(2026,10,[p])
frozen=se.people_from_request_snapshot(se.serialize_people_request_snapshot(prepared))
assert se.canonical_generation_snapshot(2026,10,[p])==se.canonical_generation_snapshot(2026,10,frozen)
changed=se.replace(p, unavailable={5,6})
assert se.canonical_generation_snapshot(2026,10,[changed])!=se.canonical_generation_snapshot(2026,10,frozen)
assert p.preferred=={5,6}, 'normalization must not mutate input'

# Execute the real orchestration prefix through work-pattern recovery, stopping
# before post assignment. Simulate timeout on both strict calls and a feasible
# first relaxed call; verify HARD inputs were not replaced or softened.
tree=ast.parse(Path(se.__file__).read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_v2564_two_phase_fair_schedule')
cut=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='post_first' for t in n.targets))
fn.body=fn.body[:cut]+[ast.Return(value=ast.Name(id='pattern',ctx=ast.Load()))]
module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
ns=dict(vars(se)); calls=[]
def work(*args,**kwargs):
    calls.append(kwargs)
    assert args[2] is people
    kwargs['diagnostics']['status']=1
    return {'structural_relaxation_mode':True} if kwargs['structural_relaxation'] else None
people=[p]
ns.update(plan_distributed_gaps=lambda *a:(set(),{},[]),
          _v2564_choose_fixed_gaps=lambda *a,**k:set(),_v2564_work_pattern=work)
exec(compile(module,'recovery-prefix','exec'),ns)
r=ns[fn.name](2026,10,people,[],{}, {},90)
assert r['strict_search_status']==1
assert [c['structural_relaxation'] for c in calls]==[False,False,True]
print('PASS canonical snapshot, genuine input change, immutable inputs, timeout fairness recovery')
