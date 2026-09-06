from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
DB=(ROOT/'db.py').read_text(encoding='utf-8')

def test_private_tab_removed():
    assert 'private_operator_tab_label="Privatūs pageidavimai"' not in APP
    assert 'st.subheader(f"Privatūs pageidavimai —' not in APP

def test_blocks_are_inside_preferences():
    p0=APP.index('# --- Preferences ---')
    p1=APP.index('# --- Settings ---')
    chunk=APP[p0:p1]
    assert 'render_sp_dream_team_settings_v25125(year,month)' in chunk
    assert 'render_operator_private_pair_preferences(year,month,active_user)' in chunk

def test_blocks_not_gated_by_advanced_mode():
    marker='# SP / ŠR papildomi planavimo blokai yra tiesiai Pageidavimuose'
    i=APP.index(marker)
    chunk=APP[i:i+700]
    assert 'advanced_mode' not in chunk
    assert 'if preference_target==active_user and active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS):' in chunk

def test_attribute_error_guard_kept():
    assert 'getattr(db,"list_operator_private_pair_preferences_v25128",None)' in APP
    assert 'getattr(db,"create_operator_private_pair_preference_v25128",None)' in APP
    assert 'getattr(db,"delete_operator_private_pair_preference_v25128",None)' in APP

def test_db_has_current_functions():
    assert 'def list_operator_private_pair_preferences_v25128' in DB
    assert 'def create_operator_private_pair_preference_v25128' in DB
    assert 'def delete_operator_private_pair_preference_v25128' in DB

def test_no_direct_fragile_list_call():
    assert 'db.list_operator_private_pair_preferences_v25128(' not in APP

def test_visible_private_wording_removed_from_editor():
    assert 'PRIDĖTI PRIVATŲ PAGEIDAVIMĄ' not in APP
    assert 'Šio mėnesio privatūs planavimo pageidavimai' not in APP

def test_release_version():
    assert 'APP_VERSION = "2.5.131 PAPILDOMI BLOKAI PAGEIDAVIMUOSE"' in APP
