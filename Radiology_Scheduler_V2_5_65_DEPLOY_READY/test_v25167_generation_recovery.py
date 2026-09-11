from pathlib import Path
import scheduler_engine as se

BASE=Path(__file__).parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
ENG=(BASE/'scheduler_engine.py').read_text(encoding='utf-8')

assert se.ENGINE_API_VERSION in {'2.5.167','2.5.168','2.5.169'}
assert se.FATIGUE_ROLLING7_HARD_CEILING_HOURS==60.0
assert ('APP_VERSION = "2.5.167 GENERATION RECOVERY"' in APP) or ('APP_VERSION = "2.5.168 FEASIBILITY FIRST"' in APP) or ('APP_VERSION = "2.5.169 POST-NIGHT 24H REST"' in APP)
assert ('EXPECTED_ENGINE_API_VERSION = "2.5.167"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.168"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.169"' in APP)
assert 'feasibility_only=False' in ENG
assert 'strict_work_pattern_same_corridor_FEASIBILITY' in ENG
assert 'feasibility_only=True' in ENG
assert ('48 val./7 d. nebėra paslėptas HARD ceiling' in APP) or ('aktyvus HARD limitas iki 60 val./7 d.' in APP)

# The active profile, not a hidden 48h clamp, determines generation hard cap.
se.set_runtime_rules(dict(se.DEFAULT_RULE_PROFILE, max_hours_rolling7=60.0))
assert se.rule_value('max_hours_rolling7')==60.0
assert min(float(se.rule_value('max_hours_rolling7')),float(se.FATIGUE_ROLLING7_HARD_CEILING_HOURS))==60.0

print('PASS V2.5.167 generation recovery')
