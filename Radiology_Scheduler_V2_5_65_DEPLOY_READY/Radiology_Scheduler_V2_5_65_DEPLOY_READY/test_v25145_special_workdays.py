from scheduler_engine import (
    Person, DEFAULT_PEOPLE, calculate_targets, absolute_unavailable_for_block,
    serialize_people_request_snapshot, people_from_request_snapshot,
    solve_schedule, make_slots,
)


def _people(special=False):
    out=[]
    for p in DEFAULT_PEOPLE:
        kw={}
        if special and p['initials']=='ŠR':
            kw={'wellness_days':{5},'qualification_days':{12}}
        out.append(Person(initials=p['initials'],name=p['name'],target_adjustment=p.get('target_adjustment',0),**kw))
    return out


def run():
    base=_people(False)
    special=_people(True)
    tb=calculate_targets(2026,10,base)
    ts=calculate_targets(2026,10,special)
    assert tb['ŠR']-ts['ŠR']==4, (tb['ŠR'],ts['ŠR'])  # 2 days × 12 h = 4 × 6 h units
    sr=next(p for p in special if p.initials=='ŠR')
    assert absolute_unavailable_for_block(sr,5,'AM')
    assert absolute_unavailable_for_block(sr,12,'PM')

    snap=serialize_people_request_snapshot(special)
    restored=people_from_request_snapshot(snap)
    rr=next(p for p in restored if p.initials=='ŠR')
    assert rr.wellness_days=={5}
    assert rr.qualification_days=={12}

    res=solve_schedule(2026,10,special,time_limit=30)
    assert res.ok, res.message
    slots={s.idx:s for s in make_slots(2026,10)}
    assert not any(slots[sid].day in {5,12} for sid,who in res.assignments.items() if who=='ŠR')
    print('V2.5.145 special workdays PASS')


if __name__=='__main__':
    run()
