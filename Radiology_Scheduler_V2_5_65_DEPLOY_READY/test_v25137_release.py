from pathlib import Path

BASE=Path(__file__).parent
APP=(BASE/'app.py').read_text(encoding='utf-8')
ENGINE=(BASE/'scheduler_engine.py').read_text(encoding='utf-8')


def test_versions_match():
    assert 'APP_VERSION = "2.5.137 PAGEIDAVIMŲ EXCEL"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.137"' in APP
    assert 'ENGINE_API_VERSION = "2.5.137"' in ENGINE


def test_preferences_excel_builder_exists():
    assert 'def build_preferences_xlsx(y,m,rows,priority_visible=False):' in APP
    assert 'add_worksheet("Pageidavimai")' in APP
    assert 'add_worksheet("Suvestinė")' in APP
    assert 'ws.autofilter(' in APP
    assert 'ws.freeze_panes(' in APP


def test_preferences_has_explicit_excel_and_csv_downloads():
    anchor='st.dataframe(style_rows(_prefs_export_df),use_container_width=True,hide_index=True)'
    assert anchor in APP
    tail=APP.split(anchor,1)[1][:2200]
    assert '"ATSISIŲSTI EXCEL (.xlsx)"' in tail
    assert 'build_preferences_xlsx(year,month,rows,priority_visible=_priority_visible)' in tail
    assert '"ATSISIŲSTI CSV (.csv)"' in tail
    assert '_prefs_export_df.to_csv(index=False)' in tail


def test_excel_export_not_gated_by_deadline():
    # The download buttons are rendered directly after the table. Deadline state
    # only controls whether the priority column is included in the snapshot.
    anchor='st.dataframe(style_rows(_prefs_export_df),use_container_width=True,hide_index=True)'
    tail=APP.split(anchor,1)[1][:2200]
    assert 'if _priority_visible:' not in tail.split('pos+=1',1)[0]


def test_priority_visibility_rule_preserved():
    assert '_priority_visible=bool(weekend_fcfs_backup_mode(year,month) and now_lt>=cutoff_pref)' in APP
    assert '**(({"Pateikimo vieta":' in APP
    assert 'if _priority_visible else {})' in APP


def test_export_has_readable_color_groups():
    for token in ['pale_red="#FDECEC"','pale_blue="#EAF3FF"','pale_yellow="#FFF6DD"','pale_green="#EAF7EF"','pale_purple="#F3EEFF"']:
        assert token in APP
    assert 'PERSON_COLORS.items()' in APP
