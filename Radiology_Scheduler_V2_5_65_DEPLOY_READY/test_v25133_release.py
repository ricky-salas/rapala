from pathlib import Path
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
sql=(ROOT/'SUPABASE_MIGRATION_V2_5_133_DREAM_TEAM_SP_SR_EDIT.sql').read_text(encoding='utf-8')

def test_dream_team_editable_by_both():
    assert 'can_edit=(active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS))' in app

def test_dream_team_hidden_from_others():
    assert 'if active_user not in (SENIOR_INITIALS,RESEARCHER_INITIALS):' in app

def test_rls_allows_both():
    assert "up.initials in ('SP','ŠR')" in sql
    assert sql.count("up.initials in ('SP','ŠR')") >= 6

def test_new_migration_present():
    assert (ROOT/'SUPABASE_MIGRATION_V2_5_133_DREAM_TEAM_SP_SR_EDIT.sql').exists()
