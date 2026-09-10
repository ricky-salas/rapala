RAPA V2.5.155 — DEPLOY-SYNC HOTFIX

SCREENSHOT ROOT CAUSE:
Streamlit is launching:
Radiology_Scheduler_V2_5_65_DEPLOY_READY/app.py

The ImportError means app.py and scheduler_engine.py in that deployed folder are not a matching pair.

DO THIS:
1. In the PRIVATE GitHub repo, open folder: Radiology_Scheduler_V2_5_65_DEPLOY_READY
2. Replace the ENTIRE folder contents with the contents from this package's folder of the same name.
3. Commit all changed files together. DO NOT commit app.py alone.
4. In Streamlit Cloud -> Manage app -> Reboot app.

NO STREAMLIT ENTRYPOINT CHANGE IS REQUIRED for this hotfix because the package intentionally preserves the old folder name.

Expected after deploy:
APP_VERSION = 2.5.155 DEPLOY-SYNC HOTFIX
ENGINE_API_VERSION = 2.5.153
EXPECTED_ENGINE_API_VERSION = 2.5.153

No new Supabase migration is required specifically for V2.5.155.
