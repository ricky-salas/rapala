from pathlib import Path
import ast, os
from datetime import date
import pandas as pd

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENG=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')

assert 'APP_VERSION = "2.5.166 GENERATION UX"' in APP
assert 'ENGINE_API_VERSION = "2.5.165"' in ENG
assert 'V25163_STRUCTURAL_FRIDAY_WATERFILL_BEFORE_SOFT' in ENG
assert 'mb.constraint(co,float(_friday_lo[pi]),float(_friday_hi[pi]))' in ENG
assert 'if _friday_exact_wishes_active:\n                # Do not force a resident onto a requested-off Friday' not in ENG
assert 'Tik esmė: ko prašei, kas gavosi ir kodėl.' in APP
assert 'Be techninių kodų ir be solverio žargono.' in APP

mod=ast.parse(APP)
names={'_is_actual_wish_row','_friendly_block_text','_friendly_date_text','_friendly_station_text','_missed_outcome_short','_missed_reason_scandi','missed_requests_scandi_df'}
body=[n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name in names]
ns={'lang':'LT','date':date,'MONTHS':{'LT':['Sausis','Vasaris','Kovas','Balandis','Gegužė','Birželis','Liepa','Rugpjūtis','Rugsėjis','Spalis','Lapkritis','Gruodis']},'os':os,'pd':pd}
exec(compile(ast.Module(body=body,type_ignores=[]),'<scandi>','exec'),ns)

reda={
 'kind':'soft_free','type':'Noriu laisvos','date':'2026-10-09','block':'FULL',
 'station':'CENTRO RO 2 (AM); CENTRO RO 1 (PM)','fulfilled':False,'included_in_score':True,
 'priority':'SOFT1_TIME_PROTECTION'
}
df=ns['missed_requests_scandi_df']([reda],'MR')
assert list(df.columns)==['Data','Pageidavimas','Kas gavosi','Kodėl']
assert df.iloc[0]['Data']=='Spalis 9 d.'
assert df.iloc[0]['Pageidavimas']=='Noriu laisvos · visa diena'
assert 'Paskirta:' in df.iloc[0]['Kas gavosi']
assert '· rytas' in df.iloc[0]['Kas gavosi'] and '· vakaras' in df.iloc[0]['Kas gavosi']
assert df.iloc[0]['Kodėl'].startswith('Penktadienių balansas')
for banned in ('SOFT1','water-fill','solver','SYSTEM'):
    assert banned not in ' '.join(str(x) for x in df.iloc[0].tolist())

weekend={
 'kind':'preferred','type':'Pageidauju dirbti','date':'2026-10-04','block':'PM','station':'—',
 'fulfilled':False,'included_in_score':True,'priority':'SOFT2_POSITIVE_PLACEMENT',
 'unmet_reason_code':'PREFERRED_CONFLICT_ASSIGNED_TO_OTHER',
 'competing_assignments':[{'department':'SPS RO budėjimai','block':'FULL','assigned_to':'VL'}]
}
df2=ns['missed_requests_scandi_df']([weekend],'MR')
assert df2.iloc[0]['Kas gavosi']=='Tinkama pamaina atiteko VL'
assert df2.iloc[0]['Kodėl'].startswith('Budėjimų balansas')
print('PASS V2.5.163 Scandinavian missed-wish audit + Friday structural fairness regression')
