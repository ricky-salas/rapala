# V2.5.134

- „Dirbti su / Dirbti be“ dabar yra **grupiniai pageidavimai**: viename pageidavime galima pasirinkti kelis žmones.
- Kiekviena grupė turi savo laikotarpį, dieną / savaitę, laiką ir vietą; grupių skaičius neribojamas.
- Vietos šiame bloke tik **CENTRO RO** ir **ADC 144/145**. „Bet kur“ pašalinta.
- CENTRO RO „Dirbti su“ grupei galima pasirinkti iki 3 kitų žmonių (iki 4 kartu su pageidavimo autoriumi).
- ADC 144/145 „Dirbti su“ yra pora: vienas žmogus gali būti 144, kitas 145 tuo pačiu laiku.
- „Dirbti be“ gali turėti kelis pasirinktus žmones; sistema stengiasi išvengti darbo su bet kuriuo iš jų pasirinktoje zonoje ir laike.
- Grupinis sluoksnis lieka galutiniame refinemente ir negali pabloginti kitų rezidentų jau užrakintų įprastų pageidavimų rezultatų.

## Duomenų bazė

Paleisti vieną naują migraciją:

`SUPABASE_MIGRATION_V2_5_134_GROUPED_PEOPLE_WISHES.sql`
