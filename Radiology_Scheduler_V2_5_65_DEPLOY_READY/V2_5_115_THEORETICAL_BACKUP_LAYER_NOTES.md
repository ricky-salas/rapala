# V2.5.115 — THEORETICAL BACKUP LAYER

This version fixes the semantic boundary between the normal SYSTEM schedule and backup/standby duties.

- A planned backup is **not work**.
- An activated-but-not-completed backup is **not work**.
- Planned/activated standby never changes `Negaliu dirbti`, `Noriu laisvos`, `Pageidauju dirbti`, workload, rest, doubles, weekend water-fill, workplace water-fill, or SYSTEM preference scores.
- Only a backup marked **COMPLETED** is a real-life cover and may enter ACTUAL work/request realization.
- NORMAL schedule validation and request audit are performed without the backup snapshot.
- Backup completeness/eligibility is a separate standby-layer audit/gate.
- Personal calendar view shows normal work and theoretical backups in visibly separate sections.
- Excel main schedule remains normal work; backup duties remain in the dedicated backup sheet.
