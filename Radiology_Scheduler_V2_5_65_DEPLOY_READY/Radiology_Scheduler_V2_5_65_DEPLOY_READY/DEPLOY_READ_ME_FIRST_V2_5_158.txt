RAPA V2.5.158 — DEPLOY TOGETHER

Streamlit deployment still uses the legacy folder path:
Radiology_Scheduler_V2_5_65_DEPLOY_READY/

Replace the WHOLE contents of that GitHub folder with the contents of this release folder.
At minimum app.py and scheduler_engine.py MUST be committed together.

Expected pair:
APP_VERSION = 2.5.158 WARDEN ONKO + SPS UG PM + GRID CLEANUP
ENGINE_API_VERSION = 2.5.158

Do not upload only app.py.
No new Supabase migration is required for V2.5.158.
