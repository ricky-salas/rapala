from pathlib import Path
import py_compile

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')


def test_version():
    assert 'APP_VERSION = "2.5.130 PRIVATŪS BLOKAI IR ŠVARI NAVIGACIJA"' in APP


def test_senior_dashboard_is_gone():
    assert 'names.append(tr("senior_dashboard"))' not in APP
    assert '# --- Senior dashboard ---' not in APP
    assert '"senior_dashboard":"Seniūnės skydas"' not in APP


def test_private_tab_is_clear_and_operator_only():
    assert 'private_operator_tab_label="Privatūs pageidavimai"' in APP
    assert 'active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS) and advanced_mode' in APP
    assert '### Nuolatinė komanda' in APP
    assert '["Noriu dirbti su","Nenoriu dirbti su"]' in APP


def test_old_db_attribute_error_path_removed():
    assert 'db.list_operator_private_pair_preferences_v25128(' not in APP
    assert 'db.create_operator_private_pair_preference_v25128(' not in APP
    assert 'db.delete_operator_private_pair_preference_v25128(' not in APP
    assert 'getattr(db,"list_operator_private_pair_preferences_v25128",None)' in APP
    assert 'operator_private_pair_preferences_v25128' in APP


def test_dream_team_has_compatibility_reader():
    assert 'def _get_sp_dream_team_config_v25130' in APP
    assert 'def _get_sp_dream_team_month_v25130' in APP
    assert 'can_edit=(active_user==SENIOR_INITIALS)' in APP


def test_private_ui_is_trimmed():
    assert '<b>Privatus operatorių sluoksnis.</b>' not in APP
    assert '<b>ŽALIAS pageidavimas:</b>' not in APP
    assert '<b>RAUDONAS pageidavimas:</b>' not in APP
    assert 'with st.expander("Rezultatas",expanded=False)' in APP


def test_python_compiles():
    for name in ('app.py','db.py','scheduler_engine.py','solver_runner.py','notification_core.py','notification_worker.py'):
        py_compile.compile(str(ROOT/name),doraise=True)
