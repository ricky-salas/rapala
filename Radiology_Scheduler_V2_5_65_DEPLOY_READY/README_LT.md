# SHIFT HAPPENS — V2.5.134

SP ir ŠR papildomi planavimo blokai yra tiesiai **„Pageidavimai“** lange ir matomi tiek Paprastame, tiek Išplėstiniame režime. Atskiro „Privatūs pageidavimai“ lango nėra.

Ši versija prideda grupinius **„Dirbti su / Dirbti be“** pageidavimus:
- viename pageidavime galima pasirinkti kelis žmones;
- kiekviena grupė gali turėti kitą dieną / savaitę / laiką;
- vietos tik **CENTRO RO** ir **ADC 144/145**;
- galima kurti tiek atskirų grupių, kiek reikia.

Dream Team redagavimas paliktas abiem — SP ir ŠR.

## Prieš naudojimą

Jei dar nepaleistos ankstesnės migracijos, paleiskite jas eilės tvarka. Šiai versijai papildomai būtina:

`SUPABASE_MIGRATION_V2_5_134_GROUPED_PEOPLE_WISHES.sql`

Diegiant pakeiskite visą paketą, kad `app.py`, `db.py`, `scheduler_engine.py` ir `solver_runner.py` būtų iš tos pačios versijos.
