from pathlib import Path

BASE=Path(__file__).parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
DB=(BASE/'db.py').read_text(encoding='utf-8')

assert ('APP_VERSION = "2.5.167 GENERATION RECOVERY"' in APP) or ('APP_VERSION = "2.5.168 FEASIBILITY FIRST"' in APP) or ('APP_VERSION = "2.5.169 POST-NIGHT 24H REST"' in APP)
assert ('EXPECTED_ENGINE_API_VERSION = "2.5.167"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.168"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.169"' in APP)
assert '_visible_names=[_generation_label]+[n for n in _logical_names if n!=_generation_label]' in APP
assert 'tabs=[_tab_by_name[name] for name in _logical_names]' in APP
assert 'BANDYTI GERESNĮ GRAFIKĄ — SAUGOTI TIK JEI GERESNIS' in APP
assert 'IŠMESTI TIK JUODRAŠTĮ' in APP
assert 'Suprantu: bus ištrintas paskelbtas šio mėnesio grafikas' in APP
assert 'def discard_draft_only' in DB

# Generation and improve success paths must not force an extra rerun.
segment=APP[APP.index('# --- Generation ---'):APP.index('# --- Schedule ---')]
assert 'st.rerun()' in segment  # only explicit state-refresh after discard/full reset
assert 'do NOT force a second rerun here' in segment
assert 'stay in Sudarymas' in segment
print('PASS V2.5.166 generation UX')
