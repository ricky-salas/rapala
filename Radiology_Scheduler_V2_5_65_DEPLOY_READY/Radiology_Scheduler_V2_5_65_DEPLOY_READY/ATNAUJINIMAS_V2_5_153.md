# RAPA Scheduler V2.5.153 — CENTRO UG RESTORE + HIDE INACTIVE

## Kas pataisyta

- **Centro UG 120kab [Rytas]** nuo 2026-10 vėl yra aktyvus darbo postas kiekvieną atvirą darbo dieną. Ankstesnis `CENTRO120_AM_REACTIVATION_START = None` buvo neteisingas fail-closed placeholderis, todėl kalendoriuje visa eilutė rodė `BLOCK`.
- **Mamografijos 31kab** nuo 2026-10 šiai rezidentų laidai lieka išjungta, tačiau kalendoriuje ir pagrindiniame Excel grafike jos eilutės neberodomos. Nebelieka sienos iš `BLOCK` langelių.
- Mamografijos slotai engine viduje palikti tik kaip **užblokuoti, paslėpti tombstone** įrašai, kad nesikeistų senų juodraščių / dublio nuorodų `slot_id`. Jie nėra aktyvi darbo talpa ir solveris jų neskiria.
- Rugsėjo ir ankstesnių istorinių mėnesių Mamografijos vaizdavimas nekeičiamas.

## Svarbu

Supabase migracijos nereikia. Deployinti `app.py` ir `scheduler_engine.py` kartu.
Po deploy spalio juodraštį rekomenduojama **pergeneruoti**, nes atsirado reali aktyvi Centro UG 120 ryto talpa.
