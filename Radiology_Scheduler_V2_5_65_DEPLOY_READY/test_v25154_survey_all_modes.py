from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text()
ENGINE=(ROOT/'scheduler_engine.py').read_text()


def test_release_contract():
    assert 'APP_VERSION = "2.5.155 DEPLOY-SYNC HOTFIX"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.153"' in APP
    assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.153"}' in APP
    assert 'ENGINE_API_VERSION = "2.5.153"' in ENGINE


def test_survey_tab_is_unconditional():
    assert 'research_nav_label = tr("research_survey")' in APP
    old='research_nav_label = tr("research") if (advanced_mode and active_user in (RESEARCHER_INITIALS,SENIOR_INITIALS)) else tr("research_survey")'
    assert old not in APP
    assert 'st.subheader(tr("research_survey"))' in APP


def test_privileged_tools_stay_gated():
    assert 'if active_user==RESEARCHER_INITIALS and advanced_mode:' in APP
    assert 'if active_user in (RESEARCHER_INITIALS,SENIOR_INITIALS) and advanced_mode:' in APP


def test_special_days_remain_separate():
    assert 'tr("special_days")' in APP
    assert 'st.subheader(("Specialios dienos" if lang=="LT" else "Special days"))' in APP
    assert 'db.get_special_workdays_v25145' in APP


if __name__=='__main__':
    test_release_contract(); test_survey_tab_is_unconditional(); test_privileged_tools_stay_gated(); test_special_days_remain_separate()
    print('V2.5.155 survey-all-modes regression PASS')
