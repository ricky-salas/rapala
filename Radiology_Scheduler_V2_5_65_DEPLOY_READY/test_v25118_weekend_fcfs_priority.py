from pathlib import Path
from scheduler_engine import (
    Person, weekend_fcfs_backup_mode, weekend_fcfs_backup_slots,
    serialize_people_request_snapshot, people_from_request_snapshot,
)

# New constitution starts with November 2026 only.
assert weekend_fcfs_backup_mode(2026,10) is False
assert weekend_fcfs_backup_mode(2026,11) is True

# Exactly 16 selectable theoretical backup positions = 8 weekend dates x AM/PM.
nov=weekend_fcfs_backup_slots(2026,11)
assert len(nov)==16
assert len({(s.day,s.block) for s in nov})==16
assert {s.day for s in nov}=={7,8,14,15,21,22,28,29}
assert all(s.block in {'AM','PM'} for s in nov)
assert all(s.weekday>=5 and s.department.startswith('SPS RO budėjimai') for s in nov)

# Five-weekend months still expose exactly 16 dubliai under the temporary one-per-person rule.
jan=weekend_fcfs_backup_slots(2027,1)
assert len(jan)==16
assert len({(s.day,s.block) for s in jan})==16

# Immutable first-submission rank/points travel with the frozen solver snapshot.
p=Person(initials='ŠR',name='Rapolas',preference_priority_points=16,preference_priority_rank=1)
snap=serialize_people_request_snapshot([p])
q=people_from_request_snapshot(snap)[0]
assert q.preference_priority_points==16
assert q.preference_priority_rank==1

app=Path('app.py').read_text(encoding='utf-8')
eng=Path('scheduler_engine.py').read_text(encoding='utf-8')
db=Path('db.py').read_text(encoding='utf-8')
mig=Path('SUPABASE_MIGRATION_V2_5_118_WEEKEND_FCFS_PRIORITY.sql').read_text(encoding='utf-8')
migb=Path('SUPABASE_MIGRATION_V2_5_118B_FCFS_CATALOG_GUARD.sql').read_text(encoding='utf-8')

assert 'APP_VERSION = "2.5.118 WEEKEND FCFS + PRIORITY POINTS"' in app
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.118"' in app
assert 'ENGINE_API_VERSION = "2.5.118"' in eng
assert 'render_fcfs_weekend_backup_selector' in app
assert 'Dubliai užpildyti' in app
assert 'Prioriteto taškai' in app
assert '#1=16' in eng or '#1=16' in mig
assert 'submission priority lock' in eng
assert '_pmult=1.0 + 0.10*_pp' in eng
assert 'claim_weekend_backup_fcfs_v25118' in db
assert 'release_weekend_backup_fcfs_v25118' in db
assert 'preference_priority_points_v25118' in db
assert 'pg_advisory_xact_lock(25118' in mig
assert 'pg_advisory_xact_lock(25119' in mig
assert 'is_fcfs_weekend_backup_slot_v25118' in migb
assert 'weekend_backup_claims_month_day_block_v25118_uidx' in migb

# New FCFS layer must be separate from normal schedule generation.
assert 'reserved=set()' in app and 'if not weekend_fcfs_backup_mode(y,m):' in app
assert 'if not weekend_fcfs_backup_mode(year,month):' in eng

print('PASS V2.5.118: exactly 16 weekend FCFS dubliai + immutable first-submission priority points')
