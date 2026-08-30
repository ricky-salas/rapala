from datetime import date
from time import perf_counter
from scheduler_engine import Person, DEFAULT_PEOPLE, solve_schedule

prefs={
'DU':{},
'GB':{'unavailable':{4,5,6}},
'GD':{},
'GE':{'soft_free':{10,11},'preferred':{8,9},'preferred_am':{7}},
'KE':{'unavailable':{24},'soft_free':{25}},
'MG':{'unavailable':{1,2,4,10,11,17,25,29}},
'MR':{'preferred':{1,2,3,6,8,9,10,11,24,27}},
'MŽ':{'unavailable':{4,5,6,18}},
'PV':{'unavailable':{11,12,13}},
'SA':{'unavailable':{21},'soft_free':{3}},
'SE':{'unavailable':{5,6}},
'SK':{'unavailable':{5,6,26,27}},
'SN':{},
'SR':{'unavailable':{5,6},'soft_free':{1}},
'ŠR':{'unavailable':{5,6,12,26},'unavailable_pm':{4,11,25}},
'VL':{'unavailable':{7,8,12,18,25,26},'preferred':{6,13,20}},
}
shift={'MŽ':2,'PV':3,'SA':3,'SR':2,'VL':2}
holiday={'PV':-1,'VL':1}
# Recurring settings from production September 2026.
# ŠR: every Tuesday + Thursday PM unavailable. VL: every Sunday prefer to work.
for d in range(1,31):
    wd=date(2026,9,d).weekday()
    if wd in (1,3): prefs['ŠR'].setdefault('unavailable_pm',set()).add(d)
    if wd==6: prefs['VL'].setdefault('preferred',set()).add(d)

people=[]
for row in DEFAULT_PEOPLE:
    i=row['initials']; p=prefs.get(i,{})
    people.append(Person(
        initials=i,name=row['name'],target_adjustment=row.get('target_adjustment',0),
        unavailable=set(p.get('unavailable',set())), unavailable_am=set(p.get('unavailable_am',set())), unavailable_pm=set(p.get('unavailable_pm',set())),
        soft_free=set(p.get('soft_free',set())), soft_free_am=set(p.get('soft_free_am',set())), soft_free_pm=set(p.get('soft_free_pm',set())),
        preferred=set(p.get('preferred',set())), preferred_am=set(p.get('preferred_am',set())), preferred_pm=set(p.get('preferred_pm',set())),
        shift_length_preference=shift.get(i,0), holiday_preference=holiday.get(i,0),
    ))

t0=perf_counter(); r=solve_schedule(2026,9,people,time_limit=90); elapsed=perf_counter()-t0
print('elapsed',round(elapsed,2),'ok',r.ok,'msg',r.message)
if not r.ok: raise SystemExit(2)
g=r.stats['global']
print('hard',g.get('hard_errors'),'rh',g.get('resident_hard_total_losses'),'fair',g.get('monthly_fairness_score'))
print('critical',g.get('critical_structural_spreads'))
print('rotation',g.get('rotation_monthly_spreads'))
print('struct_relaxed',g.get('structural_fairness_relaxed_for_zero_hard'),g.get('v25107_zero_hard_fallback_wish_mode'))
print('pref mean',g.get('mean_preference_score'),'soft',g.get('mean_soft_preference_score'))
for i in ['VL','MG','SR']:
    d=r.stats['people'][i]
    print(i,'weekends',d.get('weekend_assignments'),'Sat',d.get('saturdays'),'Sun',d.get('sundays'),'pref',d.get('preference_score'),'soft',d.get('soft_preference_score'),'rh',d.get('resident_hard_losses'))
# exact VL Sundays assigned
slot_by={s.idx:s for s in __import__('scheduler_engine').make_slots(2026,9)}
for d in [6,13,20,27]:
    xs=[(sid,slot_by[sid].block,slot_by[sid].department) for sid,w in r.assignments.items() if w=='VL' and slot_by[sid].day==d]
    print('VL Sunday',d,xs)
# MG 11 must be off
print('MG 11',[(sid,slot_by[sid].block,slot_by[sid].department) for sid,w in r.assignments.items() if w=='MG' and slot_by[sid].day==11])
