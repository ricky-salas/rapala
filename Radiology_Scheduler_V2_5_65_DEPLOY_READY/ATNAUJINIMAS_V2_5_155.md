# V2.5.155 DEPLOY-SYNC HOTFIX

Tikslas: pašalinti Streamlit Cloud ImportError, atsiradusį kai `app.py` ir `scheduler_engine.py` buvo deployinti iš skirtingų RAPA versijų.

- Programos logika paveldėta iš V2.5.154 (kuri pati remiasi stabiliu V2.5.153 scheduler engine).
- `scheduler_engine.py` nekeistas: ENGINE_API_VERSION = 2.5.153.
- `app.py` importų kontraktas patikrintas prieš tą patį `scheduler_engine.py`.
- Išsaugotas V2.5.154 pakeitimas: „Anketa“ matoma visiems tiek paprastame, tiek išplėstiniame režime.
- Išsaugotas V2.5.153 Centro UG restore / inactive Mammography hide elgesys.
- Folderio pavadinimas tyčia yra `Radiology_Scheduler_V2_5_65_DEPLOY_READY`, nes dabartinis Streamlit entrypoint vis dar rodo būtent į šį kelią.

## Deploy
GitHub'e pakeiskite VISĄ šio folderio turinį vienu commit'u. Neužtenka pakeisti tik `app.py`.
Po commit'o Streamlit Cloud atlikite Reboot app.
