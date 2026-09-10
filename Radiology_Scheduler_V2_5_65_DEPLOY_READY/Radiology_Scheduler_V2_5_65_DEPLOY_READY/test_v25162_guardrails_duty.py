from pathlib import Path
import ast, calendar
from datetime import date
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
app_src=(ROOT/'app.py').read_text()
mod=ast.parse(app_src)
fn=next(n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name=='preference_guardrail_violations_v25162')
ns={'calendar':calendar,'date':date}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<guardrail>','exec'),ns)
guard=ns['preference_guardrail_violations_v25162']

# Four-day long weekend remains a normal self-service request.
assert guard(2026,10,set(),set(),set(),{1,2,3,4},set(),set(),set(),set(),set())==[]
# Five effectively full OFF days require senior review.
assert any('5' in x and 'iš eilės' in x for x in guard(2026,10,set(),set(),set(),{1,2,3,4,5},set(),set(),set(),set(),set()))
# Same protection applies to HARD self-service inputs (e.g. 6-day block).
assert any('6' in x and 'iš eilės' in x for x in guard(2026,10,{1,2,3,4,5,6},set(),set(),set(),set(),set(),set(),set(),set()))
# All Sundays cannot be self-reserved away from the shared duty pool.
sundays={d for d in range(1,32) if date(2026,10,d).weekday()==6}
assert any('sekmadienių' in x for x in guard(2026,10,set(),set(),set(),sundays,set(),set(),set(),set(),set()))
# One weekend prefer-to-work date is allowed, two are blocked.
assert guard(2026,10,set(),set(),set(),set(),set(),set(),{4},set(),set())==[]
assert any('tik vieną' in x for x in guard(2026,10,set(),set(),set(),set(),set(),set(),{4,11},set(),set()))

slots=se.make_slots(2026,10)
night=[s for s in slots if s.day==30 and s.block=='NIGHT' and s.department.startswith('SPS RO naktinis budėjimas')]
assert len(night)==1
assert se.explicit_night_duty_owner(2026,10,30)=='GE'
assert se.is_duty_slot(night[0])

# Validator must fail closed for same-day extra work and next-day work after duty.
ge=se.Person('GE','Gertas Ernestas')
am30=next(s for s in slots if s.day==30 and s.block=='AM' and not s.blocked)
next31=next(s for s in slots if s.day==31 and not s.blocked)
assign={night[0].idx:'GE',am30.idx:'GE',next31.idx:'GE'}
st=se.validate_schedule(2026,10,[ge],slots,assign,{'GE':se.standard_target(2026,10)})
errs='\n'.join(st['global']['errors'])
assert 'VERY HARD duty-day exclusivity violated on day 30' in errs
assert 'VERY HARD post-duty rest violated; day 31 must be completely OFF after duty on day 30' in errs

# Month-boundary post-duty protection is also fail-closed in validation.
ge_prev=se.Person('GE','Gertas Ernestas',prior_last_day_duty=True)
am1=next(s for s in slots if s.day==1 and s.block=='AM' and not s.blocked)
st2=se.validate_schedule(2026,10,[ge_prev],slots,{am1.idx:'GE'},{'GE':se.standard_target(2026,10)})
assert any('post-duty rest violated on day 1' in e for e in st2['global']['errors'])

# Audit explanation must no longer imply the schedule existed before the request.
assert 'NEĮVYKDYTA, nes grafike šiame bloke yra paskyrimas' not in app_src
assert 'Pageidavimas buvo įvestis PRIEŠ grafiką' in app_src

print('PASS V2.5.162 guardrails + VERY HARD duty regression')
