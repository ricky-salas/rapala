from pathlib import Path
from scheduler_engine import weekend_fcfs_backup_slots, make_slots

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
SQL=(ROOT/'SUPABASE_MIGRATION_V2_5_146_SPECIAL_DAYS_AND_POSTPUB_BACKUPS.sql').read_text(encoding='utf-8')


def run():
    # October weekend duty/backup model is FULL only: no old 6 h AM/PM weekend backup path.
    slots=weekend_fcfs_backup_slots(2026,10)
    assert slots, 'October backup catalog empty'
    assert all(s.block=='FULL' for s in slots), {s.block for s in slots}
    assert all(s.workload2==4 for s in slots), {s.workload2 for s in slots}  # 12 h = 4 half-shift units
    weekend_ro=[s for s in make_slots(2026,10) if s.weekday>=5 and s.department.startswith('SPS RO budėjimai') and not s.blocked]
    assert weekend_ro and all(s.block=='FULL' for s in weekend_ro)

    # UI lifecycle: Specialios dienos are a separate tab; dubliai unlock only post-publication.
    assert 'tr("preferences"),tr("settings"),tr("special_days")' in APP
    assert '### Po grafiko paskelbimo' in APP
    assert 'Atsirakins tik paskelbus preliminarų grafiką' in APP
    assert 'Dubliai dar neaktyvūs' in APP
    assert '_bk_published=bool(db.get_schedule_state(year,month).get("has_published")) and bool(currentp)' in APP
    assert 'render_fcfs_weekend_backup_selector(year,month,active_user)' in APP

    # Old resident-facing legal/safety section name and signup flow are gone.
    assert 'Darbo teisės / poilsio saugos duomenys' not in APP
    assert 'with st.form("signup' not in APP

    # DB is the final guard: self-service + operator override both require a published schedule.
    assert SQL.count('BACKUP_ONLY_AFTER_PUBLICATION') >= 3
    assert "'self_fcfs_postpub'" in SQL
    assert 'save_my_preferences_v2595' in SQL and '_upsert_special_workdays_v25145' not in SQL

    print('V2.5.146 special-days lifecycle PASS')


if __name__=='__main__':
    run()
