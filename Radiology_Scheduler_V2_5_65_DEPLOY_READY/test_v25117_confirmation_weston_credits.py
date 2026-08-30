from pathlib import Path
src=Path('app.py').read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.117 CONFIRMATION + WESTON CREDITS"' in src
# ŠR must retain lifecycle confirmation in both interface modes.
assert 'lifecycle_operator_ui=(is_seniune_account or is_researcher_account)' in src
assert '(is_researcher_account and advanced_mode)' not in src[src.index('# V2.5.117'):src.index('st.sidebar.caption',src.index('# V2.5.117'))]
# Credits must be a normal operational tab, not advanced-only.
nav=src[src.index('names=[]'):src.index('tabs=st.tabs(names)')]
assert 'names.append(tr("credits_debts"))' in nav
assert 'names += [tr("summary"),tr("transparency"),tr("credits_debts")]' not in nav
credits=src[src.index('# --- Credits ---'):src.index('# --- Backups ---')]
assert 'with tabs[pos]:' in credits
assert 'if advanced_mode:\n    with tabs[pos]:' not in credits
assert '### WESTON balansas' in credits
assert 'Tavo balansas' in credits
assert '−{_w_total} WESTON' in credits
assert '+{_w_total} WESTON' in credits
assert 'SP tau skolinga — iš viso' in credits
assert 'Skola ŠR — iš viso' in credits
assert 'db.weston_beer_stats_v25110(year,month)' in credits
print('PASS V2.5.117: ŠR confirmation restored in Simple+Advanced; WESTON mirrored balance lives in Credits')
