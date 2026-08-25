# V2.5.82 — DEPLOY-SAFE APP + ENGINE SYNC

Root cause of the Streamlit TypeError:
- deployed app.py was V2.5.81 and passed `validation_mode=...`;
- deployed scheduler_engine.py was older and did not accept that argument.

The V2.5.81 ZIP itself contained the correct engine. The server was running a mixed deployment.

V2.5.82:
- adds ENGINE_API_VERSION = 2.5.82 to scheduler_engine.py;
- app.py requires the matching engine API;
- mixed deployment produces a clear APP / ENGINE VERSION MISMATCH message instead of the raw TypeError;
- refresh_result_payload also converts an old unexpected `validation_mode` TypeError into an explicit deployment mismatch error.

Deploy BOTH app.py and scheduler_engine.py from this same release.

All V2.5.81 ACTUAL swap/fairness behavior is preserved.
No Supabase migration is required.
