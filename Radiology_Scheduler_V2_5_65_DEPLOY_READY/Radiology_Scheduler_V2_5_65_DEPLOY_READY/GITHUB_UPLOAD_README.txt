RAPA V2.5.174 SAFE REPAIR DRAFT — ULTRA-LEAN DEPLOY BUNDLE

Deploy folder: Radiology_Scheduler_V2_5_65_DEPLOY_READY
Streamlit entrypoint stays: Radiology_Scheduler_V2_5_65_DEPLOY_READY/app.py

app.py and scheduler_engine.py are both V2.5.174.

NEW:
- Normal 0-HARD solve remains the first and preferred path.
- If it returns no verified candidate, RAPA automatically builds a SAFE REPAIR DRAFT instead of returning an empty result.
- Repair draft NEVER relaxes safety / Resident-HARD / overlap / daily-hour / rolling-7 / rest / post-NIGHT 24h / duty-day / explicit NIGHT-owner rules.
- Coverage, exact workload, Onko parity, post/fairness and other structural issues may remain as visible operator repair items.
- Repair draft is NEVER directly publishable. Grafikas shows the working schedule + repair list + a manual one-slot editor.
- Manual repair changes that create protected safety/HARD violations are blocked.
- Once manual edits reach 0 HARD, the repair draft automatically converts into a normal confirmable draft.

No Supabase migration required.
