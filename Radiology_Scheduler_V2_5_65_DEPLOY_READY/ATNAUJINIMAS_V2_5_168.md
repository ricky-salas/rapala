# V2.5.168 — FEASIBILITY FIRST

## Kas pataisyta
- Spalio ir vėlesnis tankus modelis pradeda nuo greito 0-HARD feasibility sprendinio tame pačiame penktadienių / savaitgalių fairness koridoriuje.
- Gavus incumbent, tas pats work-pattern etapas vis tiek maksimalizuoja ir užrakina tikslių SOFT-1 bei SOFT-2 pageidavimų skaičių; pateikimo eilė lieka tik equal-count tie-break.
- Jei pirmas cloud worker langas vis tiek negrąžina kandidato, atliekamas ilgesnis same-corridor feasibility retry; jokie HARD ar fairness guardrail'ai dėl timeout neplečiami.
- 60 h / rolling-7 aktyvus HARD limitas iš V2.5.167 išlieka.
- SPS RO budėjimų water-fill, duty-day exclusivity, poilsis tik po NIGHT, GE 10/30 NIGHT + 10/31 OFF, Onko ciklas ir V2.5.166 Sudarymas UX išlieka.

## Kodėl
Su realaus spalio 16/16 įvesties struktūra weighted-first kelias galėjo cloud'e timeoutinti be incumbent, nors modelis buvo feasible. Feasibility-first tas pačias taisykles randa žymiai greičiau ir tik tada optimizuoja pageidavimus.
