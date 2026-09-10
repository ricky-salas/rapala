V2.5.156 — ONKO DISPLAY FIX

Tikslas: pataisyti klaidinantį Onko RO = 0 stulpelį spalio 2026+ suvestinėse.

Kodėl taip buvo:
- iki 2026-09 variklis naudoja istorinį Onko RO 9 h FULL modelį;
- nuo 2026-10 patvirtintas Onko/TBL AM+PM modelis;
- UI vis dar rodė abi istorines kategorijas, todėl nebeaktyvus Onko RO buvo visas 0.

Pataisymas:
- lentelės dabar automatiškai rodo tik pasirinkto mėnesio aktyvius postus;
- 2026-09: Onko RO rodomas, Onko/TBL nerodomas;
- 2026-10+: Onko/TBL rodomas, senas Onko RO nerodomas;
- Mamografija nuo 2026-10 taip pat lieka paslėpta;
- Centro UG lieka aktyvus.

DEPLOY:
Pakeiskite visą GitHub folderio Radiology_Scheduler_V2_5_65_DEPLOY_READY turinį šio ZIP identiško folderio turiniu ir commitinkite kartu.
Streamlit entrypoint keisti nereikia.

Scheduling engine nekeistas: scheduler_engine.py / db.py / solver_runner.py byte-identical to V2.5.155 base.
