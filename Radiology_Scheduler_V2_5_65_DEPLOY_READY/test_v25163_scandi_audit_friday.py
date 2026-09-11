from pathlib import Path
import ast, os
from datetime import date
from types import SimpleNamespace
import pandas as pd

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENG=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')

assert ('APP_VERSION = "2.5.171 CAUSAL EXPLANATIONS"' in APP)
assert 'ENGINE_API_VERSION = "2.5.171"' in ENG
assert 'V25163_STRUCTURAL_FRIDAY_WATERFILL_BEFORE_SOFT' in ENG
assert 'mb.constraint(co,float(_friday_lo[pi]),float(_friday_hi[pi]))' in ENG
assert 'Tik esmė: ko prašei, kas gavosi ir kodėl.' in APP

mod=ast.parse(APP)
names={
    '_is_actual_wish_row','_friendly_block_text','_friendly_date_text','_friendly_station_text',
    '_missed_outcome_short','_missed_explanation_context','_tier_proof_sentence',
    '_missed_reason_scandi','missed_requests_scandi_df'
}
body=[n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name in names]
ns={'lang':'LT','date':date,'MONTHS':{'LT':['Sausis','Vasaris','Kovas','Balandis','Gegužė','Birželis','Liepa','Rugpjūtis','Rugsėjis','Spalis','Lapkritis','Gruodis']},'os':os,'pd':pd}
exec(compile(ast.Module(body=body,type_ignores=[]),'<scandi>','exec'),ns)

result=SimpleNamespace(stats={
    'global':{
        'friday_entitlement_lo':{'GE':6},'friday_entitlement_hi':{'GE':7},
        'soft_count_rank_locks_v25152':{
            'SOFT1':{'max_count':18,'request_count':22},
            'SOFT2':{'max_count':24,'request_count':25},
        },
        'submission_rank_is_tiebreak_only':True,
        'sps_ro_duty_floor':0,'sps_ro_duty_ceil':1,
    },
    'people':{
        'GE':{'friday_assignments':6,'weekend_assignments':1,'sps_ro_duty_assignments':1},
        **{f'X{i}':{'weekend_assignments':1} for i in range(15)}
    }
})

ge={
 'kind':'soft_free','type':'Noriu laisvos','date':'2026-10-23','block':'FULL',
 'station':'SPS UG 1035kab (PM); 145kab (AM)','fulfilled':False,'included_in_score':True,
 'priority':'SOFT1_TIME_PROTECTION'
}
df=ns['missed_requests_scandi_df']([ge],'GE',result)
assert list(df.columns)==['Data','Pageidavimas','Kas gavosi','Kodėl']
assert df.iloc[0]['Data']=='Spalis 23 d.'
assert df.iloc[0]['Pageidavimas']=='Noriu laisvos · visa diena'
assert df.iloc[0]['Kas gavosi'].startswith('Paskirta 12 h diena:')
assert '145 kab. · rytas' in df.iloc[0]['Kas gavosi']
assert 'SPS UG 1035 kab. · vakaras' in df.iloc[0]['Kas gavosi']
why=df.iloc[0]['Kodėl']
assert 'DAR PRIEŠ grafiką' in why
assert '6–7 penktadienio darbo blokai' in why
assert 'maksimaliai galėjo įvykdyti 18' in why
assert 'Pateikimo eilė naudota tik' in why
# The resulting assignment may be displayed as evidence, but it must never be the reason.
assert 'nes grafike' not in why.lower()
assert 'paskirta:' not in why.lower()
for banned in ('SOFT1','water-fill','solver'):
    assert banned not in why

print('PASS retained Scandinavian UI + V2.5.171 causal Friday explanation')
