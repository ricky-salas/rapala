from datetime import date
from collections import Counter, defaultdict
from scheduler_engine import Person, DEFAULT_PEOPLE, solve_schedule, make_slots, backup_required_slot, backup_best_effort_slot, hard_unavailable_for_block, blocks_overlap

prefs={
'DU':{},'GB':{'unavailable':{4,5,6}},'GD':{},'GE':{'soft_free':{10,11},'preferred':{8,9},'preferred_am':{7}},
'KE':{'unavailable':{24},'soft_free':{25}},'MG':{'unavailable':{1,2,4,10,11,17,25,29}},
'MR':{'preferred':{1,2,3,6,8,9,10,11,24,27}},'MŽ':{'unavailable':{4,5,6,18}},
'PV':{'unavailable':{11,12,13}},'SA':{'unavailable':{21},'soft_free':{3}},'SE':{'unavailable':{5,6}},
'SK':{'unavailable':{5,6,26,27}},'SN':{},'SR':{'unavailable':{5,6},'soft_free':{1}},
'ŠR':{'unavailable':{5,6,12,26},'unavailable_pm':{4,11,25}},'VL':{'unavailable':{7,8,12,18,25,26},'preferred':{6,13,20}},}
shift={'MŽ':2,'PV':3,'SA':3,'SR':2,'VL':2}; holiday={'PV':-1,'VL':1}
for d in range(1,31):
    wd=date(2026,9,d).weekday()
    if wd in (1,3): prefs['ŠR'].setdefault('unavailable_pm',set()).add(d)
    if wd==6: prefs['VL'].setdefault('preferred',set()).add(d)
people=[]
for row in DEFAULT_PEOPLE:
    i=row['initials']; q=prefs.get(i,{})
    people.append(Person(initials=i,name=row['name'],target_adjustment=row.get('target_adjustment',0),
        unavailable=set(q.get('unavailable',set())),unavailable_am=set(q.get('unavailable_am',set())),unavailable_pm=set(q.get('unavailable_pm',set())),
        soft_free=set(q.get('soft_free',set())),soft_free_am=set(q.get('soft_free_am',set())),soft_free_pm=set(q.get('soft_free_pm',set())),
        preferred=set(q.get('preferred',set())),preferred_am=set(q.get('preferred_am',set())),preferred_pm=set(q.get('preferred_pm',set())),
        shift_length_preference=shift.get(i,0),holiday_preference=holiday.get(i,0)))

y,m=2026,9
r=solve_schedule(y,m,people,time_limit=90)
assert r.ok
slots=make_slots(y,m)
load=Counter({p.initials:0 for p in people}); same=Counter(); pair=Counter(); desired=[]; errors=[]

def stable(*parts):
    import hashlib
    return int(hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:12],16)

def elig(sl):
    assigned=r.assignments.get(sl.idx); out=[]
    for p in people:
        if p.initials==assigned: continue
        if hard_unavailable_for_block(p,sl.day,sl.block): continue
        own=[x for x in slots if x.day==sl.day and r.assignments.get(x.idx)==p.initials]
        if any(blocks_overlap(x.block,sl.block) for x in own): continue
        out.append(p.initials)
    return out
req=[s for s in slots if backup_required_slot(s) and r.assignments.get(s.idx)]
best=[s for s in slots if backup_best_effort_slot(s) and r.assignments.get(s.idx) and s not in req]

def assign_one(sl,required=True,ceiling=None):
    e=elig(sl)
    if not e:
        if required: errors.append(sl.idx)
        return False
    fresh=[b for b in e if same[(sl.day,sl.block,b)]==0]
    e=fresh or e
    covered=r.assignments[sl.idx]
    b=min(e,key=lambda q:(load[q],same[(sl.day,sl.block,q)],pair[(q,covered)],stable(y,m,sl.day,sl.block,sl.idx,q,covered)))
    if ceiling is not None and load[b]>=ceiling:
        return False
    desired.append((sl.idx,b,1 if required else 0)); load[b]+=1; same[(sl.day,sl.block,b)]+=1; pair[(b,covered)]+=1
    return True
for sl in sorted(req,key=lambda z:(z.day,{'AM':0,'FULL':1,'PM':2}.get(z.block,9),z.idx)): assign_one(sl,True)
required_ceiling=max(load.values()) if load else 0
for sl in sorted(best,key=lambda z:(z.day,{'AM':0,'FULL':1,'PM':2}.get(z.block,9),z.idx)): assign_one(sl,False,required_ceiling)
print('ok',r.ok,'hard',r.stats['global']['hard_errors'],'errors',len(errors),'duties',len(desired))
print('backup load',dict(sorted(load.items())))
print('spread',max(load.values())-min(load.values()),'min',min(load.values()),'max',max(load.values()))
print('zero',[k for k,v in load.items() if v==0])
print('required',sum(x[2] for x in desired),'best_effort',sum(not x[2] for x in desired))
print('dream',r.stats['global'].get('dream_team_centro_weeks'),r.stats['global'].get('dream_team_centro_target_weeks'))
print('weekend cap',r.stats['global'].get('admin_weekend_spread_cap_used'))

from scheduler_engine import validate_schedule, calculate_targets
backup_rows=[]
slotmap={sl.idx:sl for sl in slots}
for sid,b,required in desired:
    sl=slotmap[sid]
    backup_rows.append({'covered_slot':sid,'planned_backup':b,'actual_backup':None,'covered_person':r.assignments.get(sid),'covered_block':sl.block})
vv=validate_schedule(y,m,people,slots,r.assignments,calculate_targets(y,m,people),satisfaction_people=people,backup_assignments=backup_rows)
print('validated hard',vv['global'].get('hard_errors'),'backup errors',[x for x in vv['global'].get('errors',[]) if 'backup' in str(x).lower() or 'dubl' in str(x).lower()][:5])
