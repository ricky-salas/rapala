# RAPA Scheduler V2.5.154 — ANKETA VISIEMS ABUOSE REŽIMUOSE

## Kas pakeista

- **Anketa** dabar rodoma kaip atskiras navigacijos langas **visiems rezidentams**.
- Ji rodoma tiek **paprastame**, tiek **išplėstiniame** režime.
- ŠR ir SP išplėstiniame režime tame pačiame lange ir toliau mato tik jiems skirtus papildomus tyrimo įrankius / suvestines.
- Paprastiems rezidentams papildomi tyrėjo ar seniūnės įrankiai **neatsiveria**.
- **Specialios dienos** lieka atskirame lange ir nėra grąžinamos į Pageidavimus.

## Stabilumo principas

Šis leidimas yra UI / prieigos matomumo pakeitimas ant **V2.5.153** bazės. Scheduling engine nekeistas ir lieka **ENGINE API 2.5.153**, kad nebūtų fairness, Centro UG, neaktyvių postų, HARD ar solverio regresijos.
