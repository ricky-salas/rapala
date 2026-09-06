from pathlib import Path

base=Path(__file__).parent
app=(base/'app.py').read_text(encoding='utf-8')
engine=(base/'scheduler_engine.py').read_text(encoding='utf-8')

assert 'APP_VERSION = "2.5.121 LT PHASE NAMES + MONTHLY PRIORITY RESET"' in app
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.121"' in app
assert 'ENGINE_API_VERSION = "2.5.121"' in engine

# Live, visible, second-by-second lifecycle clock.
assert 'def render_live_cycle_countdown' in app
assert 'setInterval(tick,1000)' in app
assert '1 etapas · Pageidavimų teikimas' in app
assert '2 etapas · Apsikeitimų laikotarpis' in app
assert '3 etapas · Seniūnės galutinė peržiūra' in app
assert 'render_live_cycle_countdown(year,month,operator=lifecycle_operator_ui)' in app

# Generation is draft-only; publication is a separate operator decision.
assert '_auto_published' not in app
assert '1/2 — Paskelbti preliminarų grafiką' in app
assert 'GENERATE / REBUILD' in app

# Automatic FCFS cycle has exactly the intended publication gates:
# PRELIMINARY is explicit in swaps phase; FINAL unlocks only in senior_review.
assert '_cycle_phase!="senior_review"' in app
assert '(not _fcfs_cycle or _cycle_phase=="senior_review")' in app
assert 'if not weekend_fcfs_backup_mode(year,month) and not payload and draft_payload:' in app

# No operational email gate for the FCFS automatic lifecycle.
assert '_notification_gate=(True if _fcfs_cycle else (smtp_ok and not missing_mail))' in app

print('PASS: V2.5.121 preserves live countdown + explicit PRELIMINARY + timed FINAL gate')
