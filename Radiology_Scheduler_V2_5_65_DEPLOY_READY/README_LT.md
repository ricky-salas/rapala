# SHIFT HAPPENS — V2.5.131

## Kas pakeista

Papildomos SP / ŠR planavimo funkcijos dabar yra ten, kur jų natūraliai ieškoma — „Pageidavimai“ lange.
Atskiro „Privatūs pageidavimai“ lango nėra.

SP ir ŠR savo „Pageidavimai“ lange mato:
- „Nuolatinė komanda“;
- „Noriu dirbti su / Nenoriu dirbti su“.

Blokai rodomi tiek Paprastame, tiek Išplėstiniame režime. Paprastiems rezidentams jie nerodomi.

Jei V2.5.128 duomenų bazės migracija dar nepaleista, paleiskite:
`SUPABASE_MIGRATION_V2_5_128_OPERATOR_PRIVATE_WISHES.sql`.

Diegiant pakeiskite visą paketą, kad `app.py` ir `db.py` būtų tos pačios versijos.
