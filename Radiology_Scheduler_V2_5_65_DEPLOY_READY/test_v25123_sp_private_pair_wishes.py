from datetime import date
import json
import scheduler_engine as se


def test_private_scope_helpers():
    assert se.private_pair_scope_days({"scope_type":"month"},2026,10)==list(range(1,32))
    assert se.private_pair_scope_days({"scope_type":"day","scope_start_date":"2026-10-17"},2026,10)==[17]
    # Oct 17 2026 is Saturday; selected week resolves to Mon 12 -> Sun 18.
    assert se.private_pair_scope_days({"scope_type":"week","scope_start_date":"2026-10-17"},2026,10)==list(range(12,19))
    assert se.private_pair_scope_blocks({"block":"ANY"})==("AM","PM")
    assert se.private_pair_scope_blocks({"block":"AM"})==("AM",)


def test_private_rows_never_enter_public_request_snapshot():
    people=[]
    for row in se.DEFAULT_PEOPLE:
        people.append(se.Person(initials=row["initials"],name=row["name"],target_adjustment=row.get("target_adjustment",0)))
    sp=next(p for p in people if p.initials=="SP")
    sp.privileged_pair_preferences=[{
        "id":999,
        "preference_type":"apart",
        "target_initials":"GE",
        "scope_type":"month",
        "scope_start_date":None,
        "block":"ANY",
        "workplace":"ANY",
    }]
    snap=se.serialize_people_request_snapshot(people)
    raw=json.dumps(snap,ensure_ascii=False)
    assert "privileged_pair_preferences" not in raw
    assert '"target_initials": "GE"' not in raw
    restored=se.people_from_request_snapshot(snap)
    rsp=next(p for p in restored if p.initials=="SP")
    assert rsp.privileged_pair_preferences==[]


def test_private_pair_defaults_are_soft_only():
    p=se.Person(initials="SP",name="SP")
    assert p.privileged_pair_preferences==[]


if __name__=="__main__":
    test_private_scope_helpers()
    test_private_rows_never_enter_public_request_snapshot()
    test_private_pair_defaults_are_soft_only()
    print("PASS V2.5.123 SP PRIVATE PAIR WISHES")

def test_static_privacy_and_colored_ui_contract():
    from pathlib import Path
    root=Path(__file__).parent
    app=(root/'app.py').read_text(encoding='utf-8')
    db=(root/'db.py').read_text(encoding='utf-8')
    sql=(root/'SUPABASE_MIGRATION_V2_5_123_SP_PRIVATE_PAIR_WISHES.sql').read_text(encoding='utf-8')
    assert 'APP_VERSION = "2.5.123 SP PRIVATE PAIR WISHES"' in app
    assert 'Privilegijuoti pageidavimai' in app
    assert '#22c55e' in app and '#ef4444' in app
    assert 'Visas mėnuo' in app and 'Visa savaitė' in app and 'Viena diena' in app
    assert 'sp_private_pair_preferences_v25123' in db
    assert "up.initials='SP'" in sql
    assert 'sp_private_pair_preferences_exist_v25123' in app
    assert 'privileged_pair_preferences' not in se.serialize_people_request_snapshot([se.Person(initials='SP',name='SP')]).get('people',[{}])[0]


if __name__=="__main__":
    test_static_privacy_and_colored_ui_contract()
