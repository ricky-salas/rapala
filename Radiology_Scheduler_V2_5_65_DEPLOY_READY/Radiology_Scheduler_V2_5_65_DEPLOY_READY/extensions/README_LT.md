# RAPA Extension · grupės taisyklių paradigma

Tikslas: nebekopijuoti solverio kiekvienai rezidentų grupei. Fairness ir saugos principai išlieka viename branduolyje, o konkreti grupė aprašoma extension failu.

Extension gali aprašyti:
- grupės narius;
- darbo vietas;
- kiek žmonių reikia vienu metu;
- AM / PM / FULL / NIGHT pamainas;
- nuo kada taisyklė įsigalioja;
- savaitgalio / darbo dienų modelį;
- fairness kategorijas;
- papildomas grupės pastabas.

## Tyrimo darbo eiga
1. Įkeliamos grupės taisyklės kaip extension (JSON / Excel / Word / PDF).
2. Sistema parodo sukompiliuotą extension santrauką žmogaus patikrai.
3. Įkeliami tos grupės realūs pageidavimai.
4. Įkeliamas žmogaus sudarytas Excel grafikas ir/ar OPTO sugeneruotas Excel grafikas.
5. RAPA izoliuotai sugeneruoja savo grafiką iš identiškų extension + pageidavimų.
6. `Tyrimas → OPTO tyrimas` lange lyginami RANKA / RAPA / OPTO.

Svarbu: extension niekada tyliai nekeičia production grafiko. Tyrimo paleidimai yra sandbox ir nerašo į SYSTEM / ACTUAL.
