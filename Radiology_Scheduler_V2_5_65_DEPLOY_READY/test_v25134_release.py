from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
db=(ROOT/'db.py').read_text(encoding='utf-8')
engine=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')
sql=(ROOT/'SUPABASE_MIGRATION_V2_5_134_GROUPED_PEOPLE_WISHES.sql').read_text(encoding='utf-8')


def test_version_and_migration_present():
    assert 'APP_VERSION = "2.5.134 GRUPINIAI PAGEIDAVIMAI"' in app
    assert (ROOT/'SUPABASE_MIGRATION_V2_5_134_GROUPED_PEOPLE_WISHES.sql').exists()


def test_ui_only_real_shared_zones():
    assert 'st.selectbox("Vieta",["CENTRO RO","ADC 144/145"]' in app
    assert 'workplaces=(\n            ["ANY"' not in app


def test_ui_supports_multi_person_groups():
    assert 'st.multiselect(' in app
    assert '"Žmonės"' in app
    assert 'max_selections=max_people' in app
    assert '_create_operator_private_group_preference_v25134' in app


def test_group_storage_and_rpc():
    assert 'group_id uuid' in sql
    assert 'operator_create_private_group_preference_v25134' in sql
    assert 'p_target_initials text[]' in sql
    assert 'operator_delete_private_group_preference_v25134' in sql
    assert 'create_operator_private_group_preference_v25134' in db


def test_capacity_rules_in_db():
    assert "p_workplace='CENTRO RO' and v_count>3" in sql
    assert "p_workplace='ADC 144/145' and v_count>1" in sql


def test_engine_understands_adc_pair_zone_and_groups():
    sys.path.insert(0,str(ROOT))
    import scheduler_engine as se
    rows=[
        {'id':1,'group_id':'g1','target_initials':'SP','workplace':'ADC 144/145','preference_type':'together'},
        {'id':2,'group_id':'g1','target_initials':'GE','workplace':'ADC 144/145','preference_type':'together'},
        {'id':3,'group_id':'g2','target_initials':'PV','workplace':'CENTRO RO','preference_type':'apart'},
    ]
    groups=se.grouped_private_pair_preferences(rows)
    assert len(groups)==2
    assert groups[0]['target_initials_list']==['SP','GE']
    assert se.private_pair_workplace_categories(groups[0])==('ADC 144','ADC 145')


def test_private_layer_stays_after_public_locks():
    assert 'Final private refinement' in engine
    assert 'nobody else\'s fulfilled wish' in engine
    assert 'Final private post-label refinement' in engine


def test_dream_team_still_editable_by_sp_and_sr():
    assert 'can_edit=(active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS))' in app
