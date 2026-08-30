# V2.5.116 — DRAFT BACKUP OVERSIGHT

This version keeps the V2.5.115 semantic separation (backup = theoretical standby, not work) but moves senior oversight earlier in the lifecycle.

- The same **GENERATE / REGENERATE** click now creates both:
  1. the NORMAL SYSTEM draft; and
  2. its separate theoretical backup/standby snapshot.
- The generated backup snapshot is saved inside the draft JSON immediately.
- In **Sudarymas**, before publication, the senior now sees:
  - total AUTO backup count and resident spread;
  - a full resident × day backup matrix;
  - an expandable shift-by-shift backup table;
  - any uncovered mandatory standby positions;
  - an explicit COMPLETE warning/success state.
- Draft-time backup rows are **not** written into operational `backup_assignments` yet. This prevents pre-publication standby from becoming real operational state or entering swap/ACTUAL logic.
- On publication, the already reviewed backup plan is synchronized into operational backup assignments as before.
- Planned/activated standby remains excluded from work, workload, rest, preference satisfaction and fairness. Only COMPLETED cover becomes ACTUAL work.
