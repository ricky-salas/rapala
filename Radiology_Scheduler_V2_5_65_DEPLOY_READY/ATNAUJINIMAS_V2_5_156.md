# V2.5.156 — month-aware workplace display

Tikslinis UI pataisymas, scheduling brain nekeistas.

- Darbo vietų lentelės dabar rodo tik to mėnesio realiai aktyvius/matomus postus.
- Iki 2026-09 rodomas istorinis `Onko RO`; būsimas `Onko/TBL` nenaudojamas ir nerodomas.
- Nuo 2026-10 rodomas `Onko/TBL`; istorinis `Onko RO` neberodomas kaip klaidinantis 0 stulpelis.
- Nuo 2026-10 uždaryta Mamografija taip pat nerodoma darbo vietų suvestinėse.
- Centro UG, SPS, ADC, Vaikų UG ir visi kiti aktyvūs postai lieka nepakeisti.
- `scheduler_engine.py`, `db.py`, `solver_runner.py` nekeisti nuo V2.5.155/V2.5.153 engine bazės.
