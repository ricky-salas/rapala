from pathlib import Path
import scheduler_engine as se
BASE=Path(__file__).parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
ENG=(BASE/'scheduler_engine.py').read_text(encoding='utf-8')
assert se.ENGINE_API_VERSION in {'2.5.168','2.5.169'}
assert ('APP_VERSION = "2.5.168 FEASIBILITY FIRST"' in APP) or ('APP_VERSION = "2.5.169 POST-NIGHT 24H REST"' in APP)
assert ('EXPECTED_ENGINE_API_VERSION = "2.5.168"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.169"' in APP)
assert '_oct_feasibility_first=cohort_october_model(year,month)' in ENG
assert 'feasibility_only=bool(_oct_feasibility_first)' in ENG
assert '_retry=(42.0 if _oct_feasibility_first' in ENG
se.set_runtime_rules(dict(se.DEFAULT_RULE_PROFILE,max_hours_rolling7=60.0))
assert se.rule_value('max_hours_rolling7')==60.0
print('PASS V2.5.168 feasibility-first static gates')
