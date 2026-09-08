from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
DB=(ROOT/'db.py').read_text(encoding='utf-8')
SQL=(ROOT/'SUPABASE_MIGRATION_V2_5_148_SHIFT_GIVEAWAY_REGISTRY.sql').read_text(encoding='utf-8')


def run():
    # Resident-facing navigation: Swap is the single operational home for bilateral swaps + one-way handoff registry.
    assert '"swaps":"Swap"' in APP
    assert '"swap_title":"Swap"' in APP
    assert '### → Atiduoti pamainą' in APP
    assert 'Noriu atiduoti' in APP
    assert 'Atidaviau pamainą' in APP

    # Survey remains available to every resident in both simple and advanced modes.
    assert 'research_nav_label = tr("research") if (advanced_mode and active_user in (RESEARCHER_INITIALS,SENIOR_INITIALS)) else tr("research_survey")' in APP
    assert 'st.subheader(tr("research_title") if (advanced_mode and active_user in (RESEARCHER_INITIALS,SENIOR_INITIALS)) else tr("research_survey"))' in APP

    # Registry is deliberately audit-only; no automatic ACTUAL mutation is hidden in the create action.
    assert 'create_shift_giveaway_record_v25148' in DB
    assert 'list_shift_giveaway_records_v25148' in DB
    assert 'cancel_shift_giveaway_record_v25148' in DB
    assert 'audit/registration layer. It never mutates ACTUAL by itself' in APP

    # DB privacy and lifecycle guards.
    assert "up.initials in ('SP','ŠR')" in SQL
    assert 'up.initials=donor_initials' in SQL
    assert 'up.initials=recipient_initials' in SQL
    assert 'GIVEAWAY_ONLY_AFTER_PUBLICATION' in SQL
    assert 'GIVEAWAY_SLOT_NOT_OWNED_BY_CURRENT_USER' in SQL
    assert "record_type in ('offer','handed_off')" in SQL
    assert 'registered_at timestamptz' in SQL

    print('V2.5.148 Swap + handoff registry PASS')


if __name__=='__main__':
    run()
