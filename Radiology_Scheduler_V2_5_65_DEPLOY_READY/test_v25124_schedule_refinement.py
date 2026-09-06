from pathlib import Path
import json
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENG=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')
MLT=(ROOT/'manual_lt.md').read_text(encoding='utf-8')
MEN=(ROOT/'manual_en.md').read_text(encoding='utf-8')

# Generic public build name does not disclose the private mechanism.
assert 'APP_VERSION = "2.5.124 SCHEDULE REFINEMENT"' in APP
assert 'SP PRIVATE PAIR WISHES' not in APP

# SP editor remains private/colored and supports month/week/day scopes.
assert 'Privatūs planavimo pageidavimai' in APP
assert '#22c55e' in APP and '#ef4444' in APP
for label in ('Visas mėnuo','Visa savaitė','Viena diena'):
    assert label in APP

# The private rows still never enter the public request snapshot.
people=[se.Person(initials=r['initials'],name=r['name'],target_adjustment=r.get('target_adjustment',0)) for r in se.DEFAULT_PEOPLE]
sp=next(p for p in people if p.initials=='SP')
sp.privileged_pair_preferences=[{
    'id':999,'preference_type':'apart','target_initials':'GE','scope_type':'month',
    'scope_start_date':None,'block':'ANY','workplace':'ANY'
}]
snap=se.serialize_people_request_snapshot(people)
raw=json.dumps(snap,ensure_ascii=False)
assert 'privileged_pair_preferences' not in raw
assert 'target_initials' not in raw

# V2.5.124 contract: private variables have zero weight in the ordinary group solve.
assert '_SP_PRIVATE_PAIR_WEIGHT' not in ENG
assert 'sp_private_pair_success_vars' in ENG
assert 'Final private refinement' in ENG
assert 'Freeze exact visible request outcomes for all residents' in ENG
assert 'mb.c[_v]-=1000.0' in ENG

# Post-label refinement locks each resident's category counts before private re-labeling.
assert 'Final post-label refinement' in ENG
assert "solved category exposure count" in ENG

# Rebuild/Improve may use private result only when the complete public quality tuple ties.
assert 'new_q==old_q and is_seniune_account' in APP
assert '_replace_candidate=(new_q < old_q)' in APP

# General/public manuals do not document the private reward or its priority mechanics.
for text in (MLT,MEN):
    assert 'Privilegijuoti seniūnės pageidavimai' not in text
    assert 'Senior privileged private wishes' not in text
    assert 'secret reward' not in text.lower()

print('PASS V2.5.124: private last-stage refinement + public fairness isolation + no public rule disclosure')
