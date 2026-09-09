from pathlib import Path
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')


def run():
    assert se.ENGINE_API_VERSION == '2.5.153'
    assert 'APP_VERSION = "2.5.155 DEPLOY-SYNC HOTFIX"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.153"' in APP
    assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.153"}' in APP

    # Centro UG 120 AM is an active weekday post in the Oct-2026+ model.
    assert se.centro120_am_active(2026, 9) is True
    assert se.centro120_am_active(2026, 10) is True
    oct_slots=se.make_slots(2026,10)
    centro_am=[s for s in oct_slots if s.department.startswith('Centro UG 120') and s.block=='AM']
    assert centro_am
    assert all(not s.blocked for s in centro_am), [(s.day,s.blocked) for s in centro_am if s.blocked]

    # Mammography is retired from the Oct cohort. Internal blocked tombstones stay
    # only to preserve slot IDs, but presentation must hide them.
    mammo=[s for s in oct_slots if s.department.startswith('Mamografijos')]
    assert mammo and all(s.blocked for s in mammo)
    assert all(not se.slot_visible_in_schedule(s,2026,10) for s in mammo)

    # Historical schedule representation is unchanged.
    sep_mammo=[s for s in se.make_slots(2026,9) if s.department.startswith('Mamografijos')]
    assert sep_mammo
    assert all(se.slot_visible_in_schedule(s,2026,9) for s in sep_mammo)

    # Both Streamlit grid and XLSX export consume the visibility policy.
    assert 'if not slot_visible_in_schedule(s,y,m):' in APP
    assert 'slots=[s for s in make_slots(y,m) if slot_visible_in_schedule(s,y,m)]' in APP

    print('V2.5.153 Centro UG restore + hidden inactive Mammography PASS')


if __name__=='__main__':
    run()
