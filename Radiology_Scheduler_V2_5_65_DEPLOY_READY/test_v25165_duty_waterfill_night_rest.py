from pathlib import Path
import scheduler_engine as se

# October has 9 daytime/weekend SPS RO duties + the explicit Oct-30 NIGHT = 10.
slots=se.make_slots(2026,10)
duties=[s for s in slots if se.is_duty_slot(s) and not s.blocked]
assert len(duties)==10, [(s.day,s.department,s.block) for s in duties]
night=[s for s in duties if s.day==30 and s.block=='NIGHT']
assert len(night)==1
assert se.explicit_night_duty_owner(2026,10,30)=='GE'

# Validator semantics: daytime FULL duty does NOT force next-day off.
p=[se.Person('AA','A')]
day_full=se.Slot(0,1,3,'SPS RO budėjimai','FULL',4,True,False)
next_am=se.Slot(1,2,4,'CENTRO RO 1','AM',2,True,False)
st=se.validate_schedule(2026,10,p,[day_full,next_am],{0:'AA',1:'AA'},{'AA':3})
assert not any('post-NIGHT' in e for e in st['global']['errors'])

# NIGHT duty DOES force the whole next day off.
night1=se.Slot(0,1,3,'SPS RO naktinis budėjimas','NIGHT',4,True,False)
st2=se.validate_schedule(2026,10,p,[night1,next_am],{0:'AA',1:'AA'},{'AA':3})
assert any('post-NIGHT rest violated' in e for e in st2['global']['errors'])

# Any duty remains same-calendar-day exclusive.
same_am=se.Slot(1,1,3,'CENTRO RO 1','AM',2,True,False)
st3=se.validate_schedule(2026,10,p,[day_full,same_am],{0:'AA',1:'AA'},{'AA':3})
assert any('duty-day exclusivity violated' in e for e in st3['global']['errors'])

# Full neutral October solve: with 10 duties / 16 residents each count must be 0 or 1.
inis=['DU','GB','GD','GE','KE','MG','MR','MŽ','PV','SA','SE','SN','SP','ŠR','SŠ','VL']
people=[se.Person(i,i) for i in inis]
r=se.solve_schedule(2026,10,people,time_limit=12)
assert r.ok, r.message
g=r.stats['global']
assert g['hard_errors']==0, g['errors']
assert g['sps_ro_duty_total_slots']==10
assert g['sps_ro_duty_floor']==0 and g['sps_ro_duty_ceil']==1
assert g['sps_ro_duty_waterfill_passed'] is True
assert max(g['sps_ro_duty_counts'].values())<=1
assert sum(g['sps_ro_duty_counts'].values())==10
sm={s.idx:s for s in slots}
ge30=[sm[sid] for sid,ini in r.assignments.items() if ini=='GE' and sm[sid].day==30]
ge31=[sm[sid] for sid,ini in r.assignments.items() if ini=='GE' and sm[sid].day==31]
assert len(ge30)==1 and ge30[0].block=='NIGHT'
assert ge31==[]

# Taisyklės must state the corrected semantics.
app=(Path(__file__).resolve().parent/'app.py').read_text()
assert 'VISI SPS RO BUDEJIMAI = WATER-FILL' in app
assert ('PO NAKTINIO BUDEJIMO KITA DIENA = LAISVA' in app) or ('PO 12 VAL. NIGHT = ≥24 VAL. NEPERTRAUKIAMO POILSIO' in app)
assert ('Po dieninio / savaitgalio 08:00–20:00 budėjimo automatinės kitos laisvos dienos nėra' in app) or ('Po dieninio / savaitgalio 08:00–20:00 budėjimo ši taisyklė netaikoma' in app)

print('PASS V2.5.165 duty water-fill + NIGHT-only next-day rest')
