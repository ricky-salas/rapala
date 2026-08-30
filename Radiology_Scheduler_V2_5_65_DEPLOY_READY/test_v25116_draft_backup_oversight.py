from pathlib import Path

src=Path('app.py').read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.117 CONFIRMATION + WESTON CREDITS"' in src
assert 'def backup_overview_grid(y,m,result):' in src
assert 'TEORINIS DUBLIŲ PLANAS — SENIŪNĖS PATIKRA' in src
assert 'Visas dublių sąrašas — kiekviena dengiama pamaina' in src
assert 'THEORETICAL BACKUP PLAN COMPLETE' in src

# Generation must create and freeze the draft snapshot before rendering it.
gen=src[src.index('# --- Generation ---'):src.index('# V2.5.22 — senior-only safe month reset.')]
assert 'desired,backup_errors=plan_backups(year,month,result)' in gen
assert 'result.backup_snapshot=[dict(x) for x in desired]' in gen
assert 'db.save_draft(year,month,serialize_result(result))' in gen
assert 'backup_overview_grid(year,month,dr)' in gen
assert 'backup_table(year,month,dr)' in gen

# Pre-publication oversight must remain snapshot-only: do not operationalize the
# draft by syncing backup_assignments inside the Generate button branch.
button_branch=gen[gen.index('if st.button(tr("generate_draft")'):gen.index('draft_for_improve=db.load_schedule')]
assert 'db.sync_backups(' not in button_branch
assert 'sync_backup_plan(' not in button_branch

print('PASS V2.5.116 draft-time backup generation + senior oversight is visible and non-operational')
