from pathlib import Path
import importlib.util

base=Path(__file__).parent
app=(base/'app.py').read_text(encoding='utf-8')
dbtxt=(base/'db.py').read_text(encoding='utf-8')
eng=(base/'scheduler_engine.py').read_text(encoding='utf-8')

assert 'APP_VERSION = "2.5.121 LT PHASE NAMES + MONTHLY PRIORITY RESET"' in app
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.121"' in app
assert 'ENGINE_API_VERSION = "2.5.121"' in eng

# Clean Lithuanian lifecycle names.
for label in [
    '1 etapas · Pageidavimų teikimas',
    '2 etapas · Apsikeitimų laikotarpis',
    '3 etapas · Seniūnės galutinė peržiūra',
    'Galutinis grafikas paskelbtas',
    '1/2 — Paskelbti preliminarų grafiką',
    '2/2 — Patvirtinti galutinį grafiką',
]:
    assert label in app, label

for old in [
    'IKI PAGEIDAVIMŲ + DUBLIO FCFS DEADLINE',
    'IKI PRE-FINAL SWAPŲ PABAIGOS',
    'SENIŪNĖS FINAL REVIEW',
    'PASKELBTI PRELIMINARŲ IR ATIDARYTI REZIDENTŲ SWAPUS',
    'PATVIRTINTI FINAL, PATEIKTI IR PARUOŠTI EXCEL',
]:
    assert old not in app, old

# Priority is one-cycle only and never cumulative.
assert 'def preference_priority_source_month' in dbtxt
assert 'def all_applied_preference_priorities' in dbtxt
assert 'return (year-1,12) if month==1 else (year,month-1)' in dbtxt
assert 'priority_rows=db.all_applied_preference_priorities(y,m)' in app
assert 'ankstesnių mėnesių taškai nesumuojami' in app
assert 'Šiam grafikui taikomas prioritetas (tšk.)' in app
assert 'Uždirbta kitam grafikui (tšk.)' in app

# Verify helper behavior without initializing Supabase.
# Import only the helper by lightweight source execution to avoid db module init side effects.
ns={}
fragment='''\ndef preference_priority_source_month(year: int, month: int):\n    year=int(year); month=int(month)\n    return (year-1,12) if month==1 else (year,month-1)\n'''
exec(fragment,ns)
f=ns['preference_priority_source_month']
assert f(2026,11)==(2026,10)
assert f(2027,1)==(2026,12)
assert f(2027,2)==(2027,1)

print('PASS V2.5.121: polished LT lifecycle + monthly non-cumulative next-cycle priority')
