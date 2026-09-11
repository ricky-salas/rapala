from pathlib import Path
ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENG=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')

assert ('APP_VERSION = "2.5.170 DRAFT CLEAN UI"' in APP) or ('APP_VERSION = "2.5.171 CAUSAL EXPLANATIONS"' in APP)
assert ('EXPECTED_ENGINE_API_VERSION = "2.5.170"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.171"' in APP)
assert ('COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.170"}' in APP) or ('COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.171"}' in APP)
assert ('ENGINE_API_VERSION = "2.5.170"' in ENG) or ('ENGINE_API_VERSION = "2.5.171"' in ENG)

start=APP.index('# --- Generation ---')
end=APP.index('# --- Schedule ---', start)
gen=APP[start:end]

assert 'GENERUOTI IŠ NAUJO' in gen
assert 'Juodraštis sukurtas. Eikite į Grafikas → Grafiko tvirtinimas' in gen
assert 'render_all_missed_requests_scandi(dr)' not in gen
assert 'TEORINIS DUBLIŲ PLANAS — SENIŪNĖS PATIKRA' not in gen
assert 'st.dataframe(style_schedule(schedule_grid(year,month,dr))' not in gen
assert 'BANDYTI GERESNĮ GRAFIKĄ — SAUGOTI TIK JEI GERESNIS' not in gen
assert 'SYSTEM patvirtinimas ir apsikeitimų lango atidarymas perkeltas' not in gen

# Detailed request audit already lives in Suvestinė, so it must remain there.
assert 'render_resident_wishes_audit(' in APP
assert '### JUODRAŠČIO PAGEIDAVIMŲ AUDITAS' in APP
assert 'Rodyti įvykdytus prašymus' in APP
assert 'Ko nepavyko išpildyti' in APP
print('PASS V2.5.170 clean draft UI + Summary audit retained')
