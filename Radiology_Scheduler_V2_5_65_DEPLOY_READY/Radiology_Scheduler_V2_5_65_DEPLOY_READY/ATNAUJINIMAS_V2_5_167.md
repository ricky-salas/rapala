# V2.5.167 — GENERATION RECOVERY

## Kas pataisyta

- Pašalintas paslėptas **48 val./7 d. HARD ceiling** generavimo engine.
- Generuojant dabar naudojamas **aktyvus Rule Profile `max_hours_rolling7`**, bet ne daugiau kaip 60 val./7 d.
- ~40 val./7 d. išlieka planavimo tikslas; **>48 val. yra aiškus workload/fatigue perspėjimas ir optimizavimo avoidance**, bet ne automatinis neįmanomumo įrodymas.
- Jei sudėtingas weighted solve timeoutina be kandidato, engine pakartoja **tą patį HARD + Friday/weekend fairness koridorių** su greitu feasibility objective. Timeout neleidžia praplėsti fairness koridoriaus.
- SPS RO budėjimų HARD water-fill, duty-day exclusivity, NIGHT-only next-day OFF, GE 2026-10-30 NIGHT + 10-31 OFF, Onko ciklas, Friday fairness ir pageidavimų rangai lieka.

## Patikra

- Python compile: PASS.
- V2.5.165 duty regression: PASS.
- V2.5.163 Scandi audit/Friday regression: PASS.
- V2.5.161 RESEARCH isolation regression: PASS.
- V2.5.166 generation UX regression: PASS.
- Isolated `solver_runner.py` API 2.5.167 smoke test: PASS.
- 2026-10 actual-input-like regression su 16 rezidentų, realiomis dabartinėmis HARD/SOFT datomis, September Onko seed ir aktyviu 60h profile: **OK, 0 HARD**, duty water-fill 10 skirtingų rezidentų.
