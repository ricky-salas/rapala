# V2.5.109 — EXCEL SCHEDULE EXPORT

## User-visible change
The schedule is now explicitly downloadable as a formatted `.xlsx` workbook anywhere the operator needs it, instead of relying on Streamlit's built-in CSV-only table toolbar.

### Sudarymas / Generation
After a SYSTEM draft is generated, the visible schedule grid is followed by:
- DOWNLOAD EXCEL (.xlsx)
- DOWNLOAD CSV (.csv)

### Grafikas → Grafiko tvirtinimas / Schedule → Finalization
The candidate can be exported before confirmation whether it is still a SYSTEM draft or already the working ACTUAL schedule.

### ACTUAL
The existing ACTUAL Excel/CSV export is retained through the shared export helper.

### FINAL
The administration FINAL Excel remains available and FINAL CSV is now shown beside it.

## Excel content
Uses the existing formatted `build_xlsx` path:
- colored schedule grid
- Summary sheet
- Backups sheet
- status label in workbook title

## Database
No Supabase migration required.

## Engine
No solver logic changed. `scheduler_engine.py` remains API 2.5.108; app package version is 2.5.109.
