from pathlib import Path
import ast, os
from datetime import date
from types import SimpleNamespace
import pandas as pd
ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENG=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.171 CAUSAL EXPLANATIONS"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.171"' in APP
assert 'ENGINE_API_VERSION = "2.5.171"' in ENG
assert 'a post-generation assignment is NEVER used as the' in APP
mod=ast.parse(APP)
names={'_is_actual_wish_row','_friendly_block_text','_friendly_date_text','_friendly_station_text','_missed_outcome_short','_missed_explanation_context','_tier_proof_sentence','_missed_reason_scandi','missed_requests_scandi_df'}
body=[n for n in mod.body if isinstance(n,ast.FunctionDef) and n.name in names]
ns={'lang':'LT','date':date,'MONTHS':{'LT':['Sausis','Vasaris','Kovas','Balandis','Gegužė','Birželis','Liepa','Rugpjūtis','Rugsėjis','Spalis','Lapkritis','Gruodis']},'os':os,'pd':pd}
exec(compile(ast.Module(body=body,type_ignores=[]),'<v171>','exec'),ns)
res=SimpleNamespace(stats={'global':{'friday_entitlement_lo':{'GE':6},'friday_entitlement_hi':{'GE':7},'soft_count_rank_locks_v25152':{'SOFT1':{'max_count':18,'request_count':22},'SOFT2':{'max_count':24,'request_count':25}},'submission_rank_is_tiebreak_only':True,'sps_ro_duty_floor':0,'sps_ro_duty_ceil':1},'people':{'GE':{'friday_assignments':6,'weekend_assignments':1,'sps_ro_duty_assignments':1},**{f'X{i}':{'weekend_assignments':1} for i in range(15)}}})
row={'kind':'soft_free','type':'Noriu laisvos','date':'2026-10-23','block':'FULL','station':'SPS UG 1035kab (PM); 145kab (AM)','fulfilled':False,'included_in_score':True}
df=ns['missed_requests_scandi_df']([row],'GE',res)
outcome=df.iloc[0]['Kas gavosi']; why=df.iloc[0]['Kodėl']
assert outcome=='Paskirta 12 h diena: 145 kab. · rytas + SPS UG 1035 kab. · vakaras'
assert 'DAR PRIEŠ grafiką' in why
assert '6–7 penktadienio darbo blokai' in why
assert '18' in why and '22' in why
assert 'Pateikimo eilė' in why
assert 'nes grafike' not in why.lower()
assert 'paskirta:' not in why.lower()
for jargon in ('SOFT1','SOFT2','water-fill','solver'):
    assert jargon not in why
print('PASS V2.5.171 causal explanations')
