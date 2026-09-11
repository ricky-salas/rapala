from pathlib import Path
BASE=Path(__file__).resolve().parent
APP=(BASE/"app.py").read_text(encoding="utf-8")
ENGINE=(BASE/"scheduler_engine.py").read_text(encoding="utf-8")
assert ('APP_VERSION = "2.5.167 GENERATION RECOVERY"' in APP) or ('APP_VERSION = "2.5.168 FEASIBILITY FIRST"' in APP) or ('APP_VERSION = "2.5.169 POST-NIGHT 24H REST"' in APP)
assert ('EXPECTED_ENGINE_API_VERSION = "2.5.167"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.168"' in APP) or ('EXPECTED_ENGINE_API_VERSION = "2.5.169"' in APP)
assert any(v in ENGINE for v in ['ENGINE_API_VERSION = "2.5.167"','ENGINE_API_VERSION = "2.5.168"','ENGINE_API_VERSION = "2.5.169"'])
assert 'if is_researcher_account:\n    names.append("RESEARCH")' in APP
assert 'AUDIT ONLY — šis langas yra izoliuotas nuo production grafiko.' in APP
assert 'render_opto_research_workbench()' in APP
assert 'RANKA · jų pačių Excel grafikas' in APP
assert 'OPTO · OPTO sugeneruotas Excel grafikas' in APP
assert 'GENERUOTI RAPA' in APP
OPTO=(BASE/"opto_research.py").read_text(encoding="utf-8")
for forbidden in ["save_schedule", "publish_schedule", "apply_schedule_repair", "save_preference"]:
    assert forbidden not in OPTO
print("PASS V2.5.163 — ŠR RESEARCH retained and isolated")
