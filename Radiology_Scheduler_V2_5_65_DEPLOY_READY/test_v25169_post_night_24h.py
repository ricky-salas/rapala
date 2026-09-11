from pathlib import Path
import scheduler_engine as se

assert se.ENGINE_API_VERSION == "2.5.169"
assert se.POST_NIGHT_MIN_REST_HOURS == 24.0

# Universal NIGHT semantics: NIGHT 20:00-08:00 + any work next calendar day violates >=24h rest.
p=[se.Person("AA","A")]
night=se.Slot(0,1,3,"ANY NIGHT SERVICE","NIGHT",4,True,False)
next_pm=se.Slot(1,2,4,"CENTRO RO 1","PM",2,True,False)
st=se.validate_schedule(2026,10,p,[night,next_pm],{0:"AA",1:"AA"},{"AA":3})
assert any(">=24h post-NIGHT rest violated" in e for e in st["global"]["errors"]), st["global"]["errors"]

# The next-next day 08:00 is exactly 24 h after a NIGHT ending at 08:00 and is allowed.
day3_am=se.Slot(1,3,5,"CENTRO RO 1","AM",2,True,False)
st2=se.validate_schedule(2026,10,p,[night,day3_am],{0:"AA",1:"AA"},{"AA":3})
assert not any("post-NIGHT" in e for e in st2["global"]["errors"]), st2["global"]["errors"]

# A daytime 12h duty does not trigger the NIGHT-specific 24h recovery rule.
day_duty=se.Slot(0,1,3,"SPS RO budėjimai","FULL",4,True,False)
next_am=se.Slot(1,2,4,"CENTRO RO 1","AM",2,True,False)
st3=se.validate_schedule(2026,10,p,[day_duty,next_am],{0:"AA",1:"AA"},{"AA":3})
assert not any("post-NIGHT" in e for e in st3["global"]["errors"]), st3["global"]["errors"]


# Cross-month defense: a NIGHT on previous month's last day makes day 1 OFF.
p_cross=[se.Person("AA","A",prior_last_day_duty=True)]
day1=se.Slot(0,1,3,"CENTRO RO 1","AM",2,True,False)
st_cross=se.validate_schedule(2026,11,p_cross,[day1],{0:"AA"},{"AA":1})
assert any("prior-month 12h NIGHT" in e for e in st_cross["global"]["errors"]), st_cross["global"]["errors"]

# Production October: GE's explicit NIGHT still makes Oct-31 completely OFF.
slots=se.make_slots(2026,10)
people=[se.Person(i,i) for i in ['DU','GB','GD','GE','KE','MG','MR','MŽ','PV','SA','SE','SN','SP','ŠR','SŠ','VL']]
r=se.solve_schedule(2026,10,people,time_limit=12)
assert r.ok, r.message
assert r.stats['global']['hard_errors']==0, r.stats['global']['errors']
sm={s.idx:s for s in slots}
ge30=[sm[sid] for sid,ini in r.assignments.items() if ini=='GE' and sm[sid].day==30]
ge31=[sm[sid] for sid,ini in r.assignments.items() if ini=='GE' and sm[sid].day==31]
assert len(ge30)==1 and ge30[0].block=='NIGHT', ge30
assert ge31==[], ge31
assert r.stats['global']['post_night_min_rest_hours']==24.0
assert r.stats['global']['post_duty_rest_policy'].startswith('EVERY_12H_NIGHT')

app=(Path(__file__).resolve().parent/'app.py').read_text(encoding='utf-8')
assert 'PO 12 VAL. NIGHT = ≥24 VAL. NEPERTRAUKIAMO POILSIO' in app
assert 'APP_VERSION = "2.5.169 POST-NIGHT 24H REST"' in app
print('PASS V2.5.169 universal >=24h post-NIGHT rest')
