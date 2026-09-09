from datetime import date
from pathlib import Path

import scheduler_engine as se
from scheduler_engine import Person
from optus_general_engine import load_extension, extension_summary, solve_extension_preview


def people():
    return [Person(initials=p['initials'], name=p['name'], target_adjustment=int(p.get('target_adjustment',0))) for p in se.DEFAULT_PEOPLE]


def run():
    assert se.ENGINE_API_VERSION == '2.5.153'
    assert not se.night_xray_duty_active(2026,11)
    assert not se.night_xray_duty_active(2026,12)

    slots=se.make_slots(2026,10)
    active=[s for s in slots if not s.blocked]
    # no operational nights until explicit confirmation
    assert not [s for s in active if s.block=='NIGHT']
    # Mammography is absent from active cohort work
    assert not [s for s in active if s.department.startswith('Mamografijos')]
    # V2.5.153 correction: Centro UG 120 AM remains active in the Oct cohort.
    assert [s for s in active if s.department.startswith('Centro UG 120') and s.block=='AM']
    # Every open weekday: 4+4 Centro, 1+1 Onko/TBL, SPS RO AM+PM
    for d in range(1,32):
        try: wd=date(2026,10,d).weekday()
        except ValueError: continue
        if wd>=5 or d in se.public_holiday_days_in_month(2026,10): continue
        day=[s for s in active if s.day==d]
        assert len([s for s in day if s.department.startswith('CENTRO RO') and s.block=='AM'])==4
        assert len([s for s in day if s.department.startswith('CENTRO RO') and s.block=='PM'])==4
        assert len([s for s in day if s.department.startswith('Onkologinė/TBL') and s.block=='AM'])==1
        assert len([s for s in day if s.department.startswith('Onkologinė/TBL') and s.block=='PM'])==1
        assert len([s for s in day if s.department.startswith('SPS RO d.d.') and s.block=='AM'])==1
        assert len([s for s in day if s.department.startswith('SPS RO d.d.') and s.block=='PM'])==1
    wk=[s for s in active if s.weekday>=5 and s.department.startswith('SPS RO budėjimai')]
    assert wk and all(s.block=='FULL' and s.workload2==4 for s in wk)

    ext=load_extension(Path('extensions/LSMU_R1_2026_10.extension.json').read_bytes())
    sm=extension_summary(ext,2026,10)
    assert sm['people']==16 and sm['slots']>0
    preview=solve_extension_preview(ext,2026,10)
    assert preview['ok']
    assert preview['workload_spread2']<=2
    assert preview['weekend_spread']<=1

    # Real current operational solver smoke test: no preferences, October model.
    res=se.solve_schedule(2026,10,people(),time_limit=10)
    assert res.ok, res.message
    g=(res.stats or {}).get('global',{})
    assert int(g.get('hard_errors',999))==0
    assert int(g.get('resident_hard_total_losses',999) or 0)==0
    print('V2.5.143 regression checks PASS on V2.5.153')

if __name__=='__main__':
    run()
