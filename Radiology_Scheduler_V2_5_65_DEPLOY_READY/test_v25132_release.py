from pathlib import Path
ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

def test_release_version():
    assert 'APP_VERSION = "2.5.132 DISKRETIŠKI PAGEIDAVIMŲ BLOKAI"' in APP

def test_dream_team_labels_are_discreet():
    assert 'st.markdown("### Dream Team")' in APP
    assert 'st.markdown("#### CENTRO RO")' in APP
    assert 'st.markdown("#### ADC 144/145")' in APP
    assert '### Nuolatinė komanda' not in APP
    assert '#### CENTRO RO komanda' not in APP
    assert '#### ADC 144/145 komanda' not in APP

def test_pair_controls_have_no_section_heading():
    assert '### Darbas su konkrečiais žmonėmis' not in APP
    assert '#### Naujas pageidavimas' not in APP
    assert '["Dirbti su","Dirbti be"]' in APP
    assert '["Noriu dirbti su","Nenoriu dirbti su"]' not in APP

def test_sr_explanatory_caption_removed():
    assert 'ŠR paskyroje šis blokas rodomas peržiūrai' not in APP

def test_private_blocks_still_inside_preferences():
    p0=APP.index('# --- Preferences ---')
    p1=APP.index('# --- Settings ---')
    chunk=APP[p0:p1]
    assert 'render_sp_dream_team_settings_v25125(year,month)' in chunk
    assert 'render_operator_private_pair_preferences(year,month,active_user)' in chunk
