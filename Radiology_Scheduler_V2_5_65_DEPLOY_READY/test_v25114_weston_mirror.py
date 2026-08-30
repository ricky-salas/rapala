from pathlib import Path
import hashlib

base=Path(__file__).parent
app=(base/'app.py').read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.115 THEORETICAL BACKUP LAYER"' in app
assert 'SENIOR_INITIALS = "SP"' in app
assert 'RESEARCHER_INITIALS = "ŠR"' in app
assert 'WESTON_CREDITOR_INITIALS = RESEARCHER_INITIALS' in app
assert 'Tavo WESTON skola ŠR' in app
assert 'SP tau skolinga WESTON' in app
assert 'SP owes you — lifetime' in app
assert 'WESTON debt to ŠR' in app
assert 'db.record_weston_beer_click_v25110(year,month)' in app
assert 'db.weston_beer_stats_v25110(year,month)' in app
print('V2.5.115 preserves WESTON mirror static checks: PASS')
