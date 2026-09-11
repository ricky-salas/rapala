# RAPA V2.5.163 — SCANDI AUDIT + FRIDAY FAIR

- Neįvykdyti pageidavimai rodomi trumpai: **Data · Pageidavimas · Kas gavosi · Kodėl**.
- Penktadieniai išlieka struktūriškai sąžiningi; konkretūs norai maksimaliai pildomi tik šio balanso ribose.
- Visos V2.5.162 VERY HARD budėjimų taisyklės išlieka.

# RAPA Scheduler — V2.5.157 ADMIN STATIONS + NO BLOCK

## V2.5.157
- SP / administracijos spalio postų prioritetai įdėti į operacinį engine.
- MUST: CENTRO RO 4+4, SPS RO AM+PM, Centro UG 120 AM, Onkologinė/TBL, Skopijos ir budėjimai.
- II prioritetas: Vaikų UG AM, ADC AM, Centro UG 120 PM.
- III prioritetas: ADC PM ir SPS UG AM.
- SPS UG PM nuo spalio neaktyvus; Mammografiją pakeičia Skopijos I–IV 08:00–14:00.
- Skopijos įprastai: Centras 0153; 2026-10-13: konsultacinė poliklinika 209.
- BLOCK / inactive slotai žmogui rodomame grafike neberodomi.
- Budėjimų HARD logika palikta nepakeista.


## V2.5.154
- Anketa matoma visiems rezidentams tiek paprastame, tiek išplėstiniame režime.
- ŠR/SP papildomi tyrimo įrankiai lieka prieinami tik pagal rolę ir tik išplėstiniame režime.
- Scheduling engine nepakeistas: naudojamas stabilus V2.5.153 engine API.
- Paveldėti V2.5.153 Centro UG / neaktyvių postų / fairness pataisymai išsaugoti.


## V2.5.153

- Centro UG 120kab [Rytas] nuo 2026-10 yra aktyvus svarbus darbo postas.
- Mamografijos nuo 2026-10 lieka išjungta ir nebėra rodoma kaip BLOCK eilutės grafike / Excel.
- Vidiniai Mamografijos tombstone slotai palikti tik slot_id stabilumui.
- Supabase migracijos nereikia; po deploy spalio juodraštį pergeneruokite.

---

## V2.5.152 — strict fairness + wish audit

- HARD ir SOFT konfliktai normalizuojami prieš primary solverį: HARD laimi, o konfliktuojantis SOFT lieka audite, bet ne score denominator.
- Savaitgalio SOFT1/SOFT2 pageidavimai dabar yra tikri optimizer inputs, ne vien post-hoc statistika.
- Konfliktuose pirmiausia užrakinamas maksimalus įvykdytų pageidavimų skaičius, tik tada taikomas pateikimo prioritetas.
- Timeout / no-incumbent nebeleidžia automatiškai praplėsti fairness; praplėtimas galimas tik po solverio įrodyto `infeasible`.
- Penktadienio fairness tikrinamas pagal HARD-eligible entitlement; raw max–min lieka auditinis rodiklis.
- Generatorius ir validatorius dabar vienodai taiko raw weekend fairness.
- Neįvykdyto `Pageidauju dirbti` paaiškinimas atskiria „pamaina neegzistuoja“ nuo „pamaina egzistuoja, bet paskirta kitam“.
- Supabase migracijos nereikia; `app.py` ir `scheduler_engine.py` diegiami kartu.


## V2.5.151 — HARD-aware penktadienių water-fill

- `Negaliu dirbti` dabar visada riboja penktadienio fairness talpą prieš skaičiuojant floor/ceil.
- Jei rezidentas dėl HARD gali dirbti tik mažą dalį penktadienių blokų, sistema nebereikalauja neįmanomo cohort-wide penktadienio minimumo.
- Likęs penktadienio krūvis water-fill'inamas tarp realiai tinkamų rezidentų.
- 0 Resident-HARD pažeidimų išlieka publikavimo vartai.
- Pataisytas compact two-phase builder account-mode refinement API crashas.
- V2.5.150 legacy draft guard išlieka aktyvus.

## V2.5.150 — juodraščio suderinamumo saugiklis
- DB įrašo egzistavimas nebelaikomas įrodymu, kad juodraštis galiojantis.
- Kiekvienas juodraštis prieš GERINTI, preliminarų paskelbimą, SYSTEM užšaldymą ar FINAL tikrinamas su dabartiniu engine.
- 0 HARD ir 0 `Negaliu dirbti` pažeidimų yra privaloma; pasenę inputai/targetai taip pat blokuoja publikavimą.
- Negaliojantis senas juodraštis paliekamas tik auditui, bet negali būti naudojamas kaip kokybės baseline.
- Solverio timeout / no-incumbent niekada nebepateikia seno invalid juodraščio kaip dabartinio kandidato.
- Nauji kandidatai saugo tikrą `app_version`, `engine_api_version`, sugeneravimo laiką ir generation source.
- Pašalintas istorinis hard-coded `engine_stats_version = V2.5.77`; serialization dabar naudoja realią engine API versiją.

## Patvirtintas operacinis modelis nuo 2026 m. spalio
- CENTRO RO: 4 AM + 4 PM darbo dienomis.
- Onkologinė / TBL: 1 AM + 1 PM darbo dienomis.
- SPS RO: AM + PM darbo dienomis.
- Mamografija šiai laidai nuo spalio išjungta.
- Centro UG 120 AM lieka išjungtas iki tikslios aktyvavimo datos.
- Savaitgalio rentgeno budėjimas: viena 12 h 08:00–20:00 pamaina.
- Naktiniai rentgeno budėjimai neaktyvuojami, kol nėra galutinai patvirtinto starto modelio.

## OPTO tyrimas
ŠR paskyros `Tyrimas` lange yra izoliuotas trijų metodų workbench:
- `RANKA` — grupės seniūno / žmogaus sudarytas Excel grafikas;
- `RAPA` — RAPA extension engine sugeneruotas grafikas;
- `OPTO` — OPTO sugeneruotas Excel grafikas.

Visi metodai vertinami pagal tą pačią užfiksuotą grupės extension ir tą patį realių pageidavimų failą. Galima lyginti `RANKA vs RAPA`, `RANKA vs OPTO`, `RAPA vs OPTO` arba visus tris.

## Extension = kitos grupės taisyklių paradigma
Extension nėra grafikas ir nėra OPTO funkcija. Jis aprašo konkrečios grupės pasaulį:
- žmones ir jų skaičių;
- postus;
- AM / PM / FULL / NIGHT pamainas;
- kiek žmonių reikia vienu metu;
- kada taisyklė galioja;
- fairness kategorijas ir saugos ribas.

Extension gali būti įkeltas JSON, Excel, Word arba PDF formatu. Excel/JSON struktūruojami tiesiogiai; Word/PDF paverčiami juodraščiu ir prieš paleidimą turi būti patikrinti. Dabartinės I kurso grupės pavyzdys: `extensions/LSMU_R1_2026_10.extension.json`. Bendras formatas: `EXTENSION_SCHEMA.json`.

## Realių pageidavimų ir grafikų įkėlimas
Po extension įkeliami tos pačios grupės realūs pageidavimai. Tada galima:
1. įkelti jų pačių Excel grafiką;
2. įkelti OPTO sugeneruotą Excel grafiką;
3. iš identiškų įvesčių sugeneruoti RAPA grafiką;
4. palyginti vienodomis metrikomis ir eksportuoti vieną tyrimo Excel.

Visa ši dalis yra izoliuota: ji nekeičia SYSTEM, ACTUAL ar Supabase operacinio grafiko.

## 12 h režimo principas
- „Mišrus“ 6 h / 12 h režimas yra lankstus, ne privalomas 50/50 tikslas.
- Aiškiai 12 h režimą pasirinkę rezidentai gali gauti daugiau 12 h dienų nei bendras vidurkis, jei tai neblogina tikrų pageidavimų, saugumo, padengimo ar darbo krūvio.
- Nustatymai nėra įtraukiami į pageidavimų išpildymo statistiką.
- Savaitgalio „Pageidauju dirbti“ pasirinkimas: daugiausia viena konkreti šeštadienio arba sekmadienio data per mėnesį.

## Kreditai ir dubliai
- Koeficientinis kreditų bankas lieka atskiras nuo pageidavimų statistikos.
- Nuo spalio savaitgalio dublis yra tik viena pilna 12 h FULL pamaina; 6 h savaitgalio dublio kelio nebėra.
- Dubliai prieš grafiko paskelbimą yra neaktyvūs. Jie atsirakina tik paskelbus preliminarų grafiką ir tada lieka aktyvūs visą likusį tikslinį mėnesį.


## Specialios dienos
- `Specialios dienos` yra atskiras langas, ne Pageidavimų dalis.
- `Sveikatinimosi dienos` ir `Kvalifikacijos kėlimo dienos` yra apmokamos darbo dienos ne klinikoje. Jos neįeina į pageidavimų statistiką ir viena diena sumažina klinikinį mėnesio krūvį 12 val. ekvivalentu.
- Šios planuojamos dienos gali būti keičiamos iki preliminaraus grafiko paskelbimo ir kalendoriuje rodomos kaip atskira būsena.
- `Pateisinamas neatvykimas` atsirakina tik paskelbus preliminarų grafiką. Jis yra post-publication operacinis pakeitimas: pradinis paskelbtas grafikas neperrašomas, koreguojamas faktinis grafikas.
- `Darbas kitur` lieka Pageidavimų lange kaip atskiras, paprastas išankstinis saugos inputas, kad RAPA žinotų apie ilgą / naktinį darbą, kurio pati nemato.

## Anketa ir Tyrimas
- Rezidentų anketa pasiekiama visiems rezidentams tiek `Paprastame`, tiek `Išplėstiniame` režime.
- Paprastame rezidento vaizde navigacijoje ši dalis rodoma kaip `Anketa`.
- ŠR ir SP Išplėstiniame režime tame pačiame bloke papildomai gauna `Tyrimas` įrankius, įskaitant izoliuotą OPTO/RAPA/human palyginimą.

## Swap
- Pagrindinis `Apsikeitimai` langas pervadintas į `Swap`.
- Abipusis swap išlieka request → kito rezidento sutikimas → seniūnės galutinis pritaikymas.
- Tame pačiame lange pridėtas vienpusio pamainos atidavimo registras:
  - `Noriu atiduoti` — registruojamas atviras atidavimo įrašas;
  - `Atidaviau pamainą` — registruojamas gavėjo inicialas ir registracijos laikas.
- SP ir ŠR mato visos grupės atidavimo registrą. Kiti rezidentai mato tik įrašus, kuriuose jie yra donorai arba gavėjai.
- Inicialai rodomi tomis pačiomis asmeninėmis spalvomis kaip grafike.
- Atidavimo registras yra auditinis: pats savaime ACTUAL grafiko nekeičia ir todėl neapeina saugos / patvirtinimo srauto.

## Nustatymų cleanup
- Rezidento `Nustatymai` neberodo seno el. pašto / SMS / reminder valdymo; esamos backend reikšmės išsaugomos nepakeistos.
- `Pirma registracija` lieka pašalinta — visi 16 rezidentų naudoja esamas paskyras.

## Paskyrų prieiga
- `Pirma registracija` pašalinta. Visi esami rezidentai jungiasi per vienintelį `Prisijungimas` srautą.


## V2.5.162 — pageidavimų ir budėjimų konstitucija

- VALIDŪS konkretūs mėnesio pageidavimai optimizuojami su 100 % tikslu prieš penktadienių / dublių / paprastų postų kosmetinį fairness. Safety, RESIDENT HARD, mandatory coverage, exact workload ir Onko HARD lieka aukščiau.
- Anti-gaming guardrail rezidentui blokuoja tik aiškius savitarnos išnaudojimo raštus: >=5 efektyviai pilnas laisvas dienas iš eilės (skaičiuojant ir `Dirbti negaliu`, ir `Noriu laisvos` kombinacijas), visus mėnesio šeštadienius arba visus sekmadienius, bei >1 savaitgalio `Pageidauju dirbti` datą. Keturių dienų ilgas savaitgalis savaime nėra blokuojamas. Tik Seniūnė/operatorius gali įvesti išimtį su audito priežastimi; oficialiam neatvykimui naudojamos atostogų / specialių dienų funkcijos.
- VERY HARD: bet kokio RAPA budėjimo dieną negali būti jokios kitos pamainos tam pačiam rezidentui.
- VERY HARD: po SPS RO naktinio budėjimo visa kita kalendorinė diena yra LAISVA. Taisyklė galioja ir per mėnesio ribą ir nėra voluntary-swap ACK išimtis.
- 2026-10-30 `SPS RO naktinis budėjimas` HARD priskirtas GE (Gertas Ernestas); 2026-10-31 GE privalomai laisva.


## V2.5.165 — SPS RO budėjimų konstitucinės taisyklės

- **Visi SPS RO budėjimai water-fill'inami kartu.** Savaitgalio / šventinis FULL ir NIGHT yra vieno budėjimų skaitiklio dalys. Niekas negauna antro budėjimo, kol kitas HARD-tinkamas rezidentas dar neturi pirmo. Tikslus mėnesio floor/ceil koridorius yra HARD ir neplečiamas fallback režime.
- **Budėjimo diena yra išskirtinė.** Bet koks SPS RO budėjimas tą pačią kalendorinę dieną negali sutapti su jokia kita RAPA pamaina.
- **Po kiekvienos 12 val. NIGHT pamainos – ≥24 val. nepertraukiamo poilsio.** NIGHT 20:00–08:00 baigiasi kitos dienos 08:00, todėl visa ta kalendorinė diena yra ABSOLUTE OFF; ankstyviausia kita RAPA pamaina gali prasidėti tik dar kitos dienos 08:00. Taisyklė taikoma visoms NIGHT pamainoms ir per mėnesio ribą. Dieninis / savaitgalio 08:00–20:00 budėjimas šios automatinės 24 val. poilsio taisyklės nesukuria.
- **2026-10-30 GE NIGHT → 2026-10-31 GE OFF** lieka HARD.


## V2.5.167 — GENERATION RECOVERY

Generuojant rolling-7 HARD limitas imamas iš aktyvaus Rule Profile (iki 60 val./7 d.). ~40 val. yra planavimo tikslas, o >48 val. rodomas kaip didelio krūvio perspėjimas / avoidance, ne paslėptas HARD ceiling. Weighted solveriui timeoutinus be kandidato, RAPA bando tą patį Friday/weekend fairness koridorių su feasibility recovery ir fairness dėl timeouto neplatina.
