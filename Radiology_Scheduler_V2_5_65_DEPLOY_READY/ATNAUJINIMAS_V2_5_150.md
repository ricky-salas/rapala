# V2.5.150 — DRAFT COMPATIBILITY GUARD

## Problema
Senas DB juodraštis galėjo likti iš ankstesnio solverio. Kai naujas solveris negaudavo patvirtinto kandidato per retry/watchdog laiką, senas įrašas būdavo paliekamas nepakeistas. UI tada jį vis tiek vadindavo egzistuojančiu juodraščiu ir leisdavo GERINTI / publikavimo veiksmus, nors dabartinis engine jau galėjo rasti HARD arba `Negaliu dirbti` pažeidimų.

## Pataisyta
- `draft_compatibility_status()` kiekvieną stored draft fail-closed revaliduoja su CURRENT engine.
- Publishable draft privalo turėti:
  - `hard_errors == 0`;
  - `Negaliu dirbti` pažeidimų == 0;
  - dabartinius workload targetus;
  - nepasikeitusį original request snapshotą.
- Invalid / outdated draft:
  - aiškiai žymimas `LEGACY / INVALID DRAFT — SKELBTI NEGALIMA`;
  - paliekamas tik auditui;
  - negali būti `PERTIKRINTI / GERINTI` baseline;
  - negali atrakinti SYSTEM freeze, PRELIMINARY ar FINAL.
- Timeout / no-incumbent dabar aiškiai rodo `NAUJAS GRAFIKAS NESUGENERUOTAS`; senas invalid DB row nėra pristatomas kaip validus kandidatas.
- Naujas validus GENERATE/IMPROVE kandidatas gauna provenance: app version, engine API version, generation timestamp, generation source.
- `scheduler_engine.serialize_result()` nebeturi hard-coded `V2.5.77`; įrašo tikrą `ENGINE_API_VERSION`.

## Versijos
- App: `2.5.150 DRAFT COMPATIBILITY GUARD`
- Scheduler API: `2.5.150`
- DB migracija: nereikalinga; provenance saugomas schedule JSON payload'e.
