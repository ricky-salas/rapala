from datetime import date
from scheduler_engine import Person, DEFAULT_PEOPLE, solve_schedule, make_slots, validate_schedule, blocks_overlap

prefs={
'DU':{},'GB':{'unavailable':{4,5,6}},'GD':{},'GE':{'soft_free':{10,11},'preferred':{8,9},'preferred_am':{7}},
'KE':{'unavailable':{24},'soft_free':{25}},'MG':{'unavailable':{1,2,4,10,11,17,25,29}},
'MR':{'preferred':{1,2,3,6,8,9,10,11,24,27}},'MŽ':{'unavailable':{4,5,6,18}},
'PV':{'unavailable':{11,12,13}},'SA':{'unavailable':{21},'soft_free':{3}},'SE':{'unavailable':{5,6}},
'SŠ':{'unavailable':{5,6,26,27}},'SN':{},'SP':{'unavailable':{5,6},'soft_free':{1}},
'ŠR':{'unavailable':{5,6,12,26},'unavailable_pm':{4,11,25}},'VL':{'unavailable':{7,8,12,18,25,26},'preferred':{6,13,20}},}
shift={'MŽ':2,'PV':3,'SA':3,'SP':2,'VL':2}; holiday={'PV':-1,'VL':1}
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

# September baseline regression: normal schedule itself remains unchanged/valid.
assert r.stats['global']['hard_errors']==0
assert int(r.stats['global'].get('dream_team_centro_weeks',0))==int(r.stats['global'].get('dream_team_centro_target_weeks',0))==5
assert int(r.stats['global'].get('admin_weekend_spread_cap_used',-1))==4
_total=_honored=_missed=0
_misses=[]
for _ini,_pd in r.stats['people'].items():
    for _rr in (_pd.get('request_detail_rows') or []):
        if not _rr.get('included_in_score'):
            continue
        _total+=1
        if _rr.get('fulfilled'):
            _honored+=1
        else:
            _missed+=1; _misses.append((_ini,_rr.get('kind'),_rr.get('day')))
assert (_total,_honored,_missed)==(77,71,6), (_total,_honored,_missed,_misses)
assert all(k=='preferred' for _,k,_ in _misses), _misses
slot_map={s.idx:s for s in slots}
ge_slots=[s for s in slots if r.assignments.get(s.idx)=='GE']

def find_backup_target(day):
    # Need a covered shift whose block does not overlap GE's normal work on that date.
    own=[s for s in ge_slots if s.day==day]
    for s in slots:
        if s.day!=day or s.idx not in r.assignments or r.assignments[s.idx]=='GE':
            continue
        if any(blocks_overlap(x.block,s.block) for x in own):
            continue
        return s
    return None

def find_backup_target_for(person,day):
    own=[s for s in slots if s.day==day and r.assignments.get(s.idx)==person]
    for sl in slots:
        if sl.day!=day or sl.idx not in r.assignments or r.assignments[sl.idx]==person:
            continue
        if any(blocks_overlap(x.block,sl.block) for x in own):
            continue
        return sl
    return None

# Reproduce the exact semantic shape seen in the V2.5.114 screenshot: planned
# standbys on soft-free dates for GE/KE/SP must NOT create missed wishes.
standby_cases=[('GE',10),('GE',11),('KE',25),('SP',1)]
backup=[]
for who,day in standby_cases:
    sl=find_backup_target_for(who,day)
    assert sl is not None,(who,day)
    backup.append({
        'covered_slot':sl.idx,'covered_person':r.assignments[sl.idx],
        'planned_backup':who,'actual_backup':None,
        'activated_at':None,'completed_at':None,
    })

stats=validate_schedule(y,m,people,slots,r.assignments,r.targets,satisfaction_people=people,backup_assignments=backup)
for who,day in standby_cases:
    rows=[x for x in stats['people'][who].get('request_detail_rows',[]) if x.get('kind')=='soft_free' and x.get('day')==day]
    assert rows and rows[0]['fulfilled'] is True,(who,day,rows)
    assert 'DUBLIS' not in str(rows[0].get('station','')),(who,day,rows[0])

# Wish totals stay 71/77 even though four theoretical backups sit on requested-off days.
_t=_h=_m=0
for _pd in stats['people'].values():
    for _rr in (_pd.get('request_detail_rows') or []):
        if _rr.get('included_in_score'):
            _t+=1; _h+=int(bool(_rr.get('fulfilled'))); _m+=int(not bool(_rr.get('fulfilled')))
assert (_t,_h,_m)==(77,71,6),(_t,_h,_m)
assert stats['global']['planned_backups_affect_request_score'] is False
assert stats['global']['hard_errors']==0

# Activated standby is still not real work.
backup[0]['activated_at']='2026-09-10T00:00:00Z'
stats2=validate_schedule(y,m,people,slots,r.assignments,r.targets,satisfaction_people=people,backup_assignments=backup,validation_mode='voluntary_swap_actual')
ge2=stats2['people']['GE']
soft2=[x for x in ge2.get('request_detail_rows',[]) if x.get('kind')=='soft_free' and x.get('day')==10]
assert soft2 and soft2[0]['fulfilled'] is True,soft2

# COMPLETED cover is real ACTUAL work and may change actual realization.
backup[0]['completed_at']='2026-09-10T01:00:00Z'
stats3=validate_schedule(y,m,people,slots,r.assignments,r.targets,satisfaction_people=people,backup_assignments=backup,validation_mode='voluntary_swap_actual')
ge3=stats3['people']['GE']
soft3=[x for x in ge3.get('request_detail_rows',[]) if x.get('kind')=='soft_free' and x.get('day')==10]
assert soft3 and soft3[0]['fulfilled'] is False,soft3
assert 'REALIAI PAVADAVO' in str(soft3[0].get('station','')),soft3[0]
print('PASS theoretical standby is isolated; COMPLETED cover alone becomes ACTUAL work')
