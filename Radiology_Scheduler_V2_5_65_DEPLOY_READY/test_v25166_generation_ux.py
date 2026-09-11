from pathlib import Path
BASE=Path(__file__).parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
DB=(BASE/'db.py').read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.171 CAUSAL EXPLANATIONS"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.171"' in APP
assert '_visible_names=[_generation_label]+[n for n in _logical_names if n!=_generation_label]' in APP
assert 'tabs=[_tab_by_name[name] for name in _logical_names]' in APP
assert 'GENERUOTI IŠ NAUJO' in APP
assert 'Suprantu: bus ištrintas paskelbtas šio mėnesio grafikas' in APP
assert 'def discard_draft_only' in DB
print('PASS retained generation UX through V2.5.171')
