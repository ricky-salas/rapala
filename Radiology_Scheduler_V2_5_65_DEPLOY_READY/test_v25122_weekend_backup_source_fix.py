from pathlib import Path
root=Path(__file__).resolve().parent
app=(root/'app.py').read_text()
sql=(root/'SUPABASE_MIGRATION_V2_5_122_WEEKEND_BACKUP_SOURCE_FIX.sql').read_text()
assert '2.5.122 WEEKEND BACKUP SOURCE FIX' in app
for value in ['self','auto','senior','self_fcfs','auto_random','operator_manual','operator_manual_swap']:
    assert f"'{value}'::text" in sql, value
assert 'weekend_backup_claims_source_check' in sql
assert '23514' in app
print('PASS V2.5.122 source constraint compatibility checks')
