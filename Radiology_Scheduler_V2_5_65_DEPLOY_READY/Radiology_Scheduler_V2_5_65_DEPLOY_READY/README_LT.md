# SHIFT HAPPENS — V2.5.136

Streamlit radiologijos rezidentų grafiko sistema.

## Šio leidimo pagrindas
- koeficientinis kreditų bankas;
- dublio pasirinkimas visą tikslinį mėnesį, nepriklausomai nuo grafiko statuso;
- pateikimo eilė skaičiuojama pagal paskutinį reikšmingą pakeitimą ir rodoma tik po termino;
- atnaujintas lietuviškas seniūnės Word vadovas.

## Diegimas
1. Diegti visą ZIP turinį kartu (`app.py`, `db.py`, `scheduler_engine.py`).
2. Supabase SQL Editor paleisti `SUPABASE_MIGRATION_V2_5_136_CREDIT_ENGINE_GUARD.sql`.
3. Perkrauti Streamlit aplikaciją.

Ankstesnių migracijų failai palikti pakete naujos aplinkos atkūrimui.

## V2.5.137 — Pageidavimų Excel eksportas

„Pageidavimai“ lange SP / ŠR gali bet kuriuo metu atsisiųsti aktualų spalvotą `.xlsx` failą. Eksportas nepriklauso nuo to, ar pageidavimų langas dar atidarytas, ar jau uždarytas. Iki 14 d. 00:00 prioritetinė eilė faile nerodoma; po termino ji įtraukiama automatiškai.
