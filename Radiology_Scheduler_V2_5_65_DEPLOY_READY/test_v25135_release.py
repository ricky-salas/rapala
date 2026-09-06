from pathlib import Path
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')

def test_version():
    assert 'APP_VERSION = "2.5.135 BE SENIŪNĖS VADOVO LANGO"' in app

def test_no_senior_guide_tab_in_navigation():
    assert 'names.append(tr("senior_guide"))' not in app

def test_no_senior_guide_render_block():
    assert '# --- Senior usability / audit guide ---' not in app
    assert 'st.subheader(tr("senior_guide"))' not in app

def test_word_guide_still_packaged():
    assert any(p.name.startswith('SHIFT_HAPPENS_SENIUNES_VADOVAS') and p.suffix.lower()=='.docx' for p in ROOT.iterdir())

def test_grouped_people_ui_preserved():
    assert 'st.selectbox("Vieta",["CENTRO RO","ADC 144/145"]' in app
    assert 'max_selections=max_people' in app

def test_dream_team_editable_by_both_preserved():
    assert 'can_edit=(active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS))' in app
