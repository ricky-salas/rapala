from pathlib import Path
import ast
import hashlib
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

assert 'APP_VERSION = "2.5.156 MONTH-AWARE POST DISPLAY"' in APP
assert 'def display_rotation_categories(y,m):' in APP
assert 'for cat in display_rotation_categories(y,m):' in APP
assert 'for cat in display_rotation_categories(year,month):' in APP

# Model truth: September uses legacy Onko RO; October uses Onko/TBL.
def active_categories(y,m):
    active=set()
    for s in se.make_slots(y,m):
        if s.blocked or not se.slot_visible_in_schedule(s,y,m):
            continue
        cat=se.rotation_category(s)
        if cat in se.ROTATION_CATEGORIES:
            active.add(cat)
    return [cat for cat in se.ROTATION_CATEGORIES if cat in active]

sep=active_categories(2026,9)
oct_=active_categories(2026,10)
assert 'Onko RO' in sep and 'Onko/TBL' not in sep, sep
assert 'Onko/TBL' in oct_ and 'Onko RO' not in oct_, oct_
assert 'Mamografijos' in sep and 'Mamografijos' not in oct_, (sep,oct_)
assert 'Centro UG' in oct_, oct_

# October oncology slots are real active AM+PM work, not zero-capacity tombstones.
oct_onko=[s for s in se.make_slots(2026,10) if se.rotation_category(s)=='Onko/TBL' and not s.blocked]
assert oct_onko
assert {s.block for s in oct_onko}=={'AM','PM'}

print('PASS V2.5.156: month-aware post display; legacy Onko RO hidden in Oct, active Onko/TBL retained')
