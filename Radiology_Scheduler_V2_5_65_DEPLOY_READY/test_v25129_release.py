from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


def test_version():
    assert 'APP_VERSION = "2.5.129 MINIMALUS ETAPŲ LAIKMATIS"' in APP


def test_countdown_is_minimal():
    start = APP.index('def render_live_cycle_countdown')
    end = APP.index('def _workflow_card', start)
    block = APP[start:end]
    assert '1 etapas · Pageidavimų teikimas' in block
    assert '2 etapas · Preliminaraus grafiko rengimas' in block
    assert '3 etapas · Apsikeitimai' in block
    assert '4 etapas · Galutinė peržiūra' in block
    assert 'Liko iki pageidavimų pateikimo pabaigos' not in block
    assert 'Vilniaus laiku' not in block
    assert 'seniūnės grafiko sudarymo ir patikros etapas' not in block
    assert 'class=\\"sub\\"' not in block


def test_minimal_visual_style():
    start = APP.index('def render_live_cycle_countdown')
    end = APP.index('def _workflow_card', start)
    block = APP[start:end]
    assert 'border-radius:9px' in block
    assert 'font-size:30px' in block
    assert 'font-weight:650' in block
    assert 'height=78' in block


def test_python_compiles():
    for name in ('app.py','db.py','scheduler_engine.py','solver_runner.py','notification_core.py','notification_worker.py'):
        py_compile.compile(str(ROOT / name), doraise=True)
