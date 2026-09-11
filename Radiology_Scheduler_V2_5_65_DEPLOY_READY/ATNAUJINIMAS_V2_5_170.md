# RAPA V2.5.170 — DRAFT CLEAN UI

- Sudarymas po sėkmingo generavimo sąmoningai paliktas minimalus: būsena, GENERUOTI IŠ NAUJO ir vienas žalias patvirtinimas.
- Žalias pranešimas aiškiai siunčia į Grafikas → Grafiko tvirtinimas arba siūlo generuoti kitą variantą.
- Iš Sudarymas pašalinti pageidavimų auditai, fairness metrikos, dublių lentelės, grafiko preview ir papildomi diagnostiniai blokai.
- Detalus pageidavimų auditas jau yra Suvestinė lange: įvykdyti / neįvykdyti prašymai, detalus rezidento drill-down ir missed-wish paaiškinimai. Todėl duomenys nedubliuojami.
- Po sėkmingo generavimo atliekamas saugus rerun; SP/ŠR Sudarymas yra pirmas tabas, todėl rodoma iškart teisinga būsena „Juodraštis“, o ne pasenęs „Nesukurtas“.
- Schedulerio logika nekeičiama; V2.5.169 24 h post-NIGHT HARD taisyklė išlaikyta. Engine API bump į 2.5.170 skirtas griežtam app/engine sinchronizavimui.
