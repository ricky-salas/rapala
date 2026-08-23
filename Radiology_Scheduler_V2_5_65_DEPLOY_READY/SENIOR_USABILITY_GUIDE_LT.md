# Seniūnės naudojimo ir audito vadovas

## 1. Kam skirtas šis įrankis

Įrankio paskirtis nėra pakeisti seniūnės sprendimą ar reikalauti aklai pasitikėti algoritmu. Jo paskirtis – didžiąją dalį pasikartojančio skaičiavimo, taisyklių derinimo ir fairness kontrolės atlikti automatiškai, o seniūnei palikti **trumpą, kryptingą išimčių auditą**.

Pagrindinis darbo principas:

**Generate → Patikrinti konkrečius teiginius → Taisyti tik išimtis → Publish → Valdyti ACTUAL pakeitimus.**

Seniūnei nereikia dar kartą perskaičiuoti viso mėnesio. Reikia patikrinti, ar keli konkretūs įrankio teiginiai sutampa su pačiu SYSTEM grafiku. **Teiginys** čia reiškia paprastą patikrinamą sakinį, pvz. „18 d. PM prašė laisvos, bet paskirtas SPS UG PM, todėl pageidavimas neįvykdytas.“

## 2. Ką verta patikrinti prieš publikavimą

### A. HARD / diagnostics
- TRUE ABSOLUTE HARD klaidų turi būti 0.
- Jei RESIDENT HARD negalėjimas neišvengiamai prarastas, turi būti nurodyta: rezidentas, data, laiko blokas, postas ir kodėl 0-loss grafikas nebuvo įmanomas.
- Mandatory SPS RO, SPS UG ir savaitgalio coverage turi būti užpildytas.

### B. Critical exposure
- SPS RO spread: 0–1.
- SPS UG spread: 0–1.
- Savaitgalių spread: 0–1.
- Turi būti vengiama bereikalingo kritinių pamainų suspaudimo tam pačiam žmogui.

### C. Krūvis ir poilsis
- Patikrinti blogiausią rolling-7 valandų rodiklį.
- Patikrinti, ar nėra akivaizdžiai neproporcingų 12 val. pamainų sekų.
- Patikrinti, ar vienas rezidentas negavo neproporcingai sunkesnės savaitės nei kiti, kai buvo alternatyvų.

### D. Preference / request satisfaction
Nereikia ranka tikrinti visų 16 rezidentų. Spot-check principu pasirinkti 3–5:
1. mažiausio satisfaction rezidentą;
2. didžiausio satisfaction rezidentą;
3. bent vieną su RESIDENT HARD;
4. 1–2 atsitiktinius / vidutinius rezidentus.

Kiekvienam pakanka patikrinti kelis konkrečius **teiginius**, pvz.:
- `RESIDENT HARD 5/5`;
- `SOFT-1 3/4`;
- `SPS RO = 2`;
- `SPS UG = 2`;
- `weekends = 1`;
- `18 d. PM: „Noriu laisvos“ — NEĮVYKDYTA, nes SYSTEM grafike paskirta SPS UG PM`.

### Kaip perskaityti vieną eilutę

Įrankis turi rodyti ne kodą ar trumpą žymą, o visą logiką:

**Ko prašė → ką grafikas paskyrė → rezultatas → kodėl → kaip patikrinti → ką būtų galima swapinti.**

Pavyzdys:

**Ko prašė:** Noriu laisvos · 2026-08-18 · PM  
**Ką rodo SYSTEM grafikas:** SPS UG (PM)  
**Rezultatas:** NEĮVYKDYTA  
**Kodėl:** pageidautame laisvame PM bloke yra persidengianti darbo pamaina.  
**Kaip patikrinti:** atverk rugpjūčio 18 d., rask rezidentą ir PM bloką. Jei SPS UG PM ten nėra, įrankio teiginys klaidingas.  
**Jei nori taisyti:** ieškok tinkamo swapo, kuris nuimtų šį SPS UG PM paskyrimą.

Jei įrankis rašo `SPS UG = 2`, SYSTEM grafike / Post Matrix turi būti lygiai du SPS UG priskyrimai tam žmogui. Tai yra toks pats konkretus teiginys, tik apie postų skaičių.

## 3. 5 minučių auditavimo seka

1. **HARD / diagnostics:** ar nėra ABSOLUTE klaidų?
2. **Post Matrix:** ar SPS RO, SPS UG ir savaitgaliai yra 0–1?
3. **Resident Stats:** kas turi didžiausią weekly load, doubles ir consecutive burden?
4. **Teiginių spot-check:** 3–5 rezidentai, keli konkretūs teiginiai kiekvienam.
5. **Grafikas / Proof:** ar suvestinės ir pats grafikas sutampa?

Jeigu šie penki punktai geri, seniūnė gauna daug stipresnį pagrindą publikuoti nei vien iš vizualinio Excel peržiūrėjimo.

## 4. Kada NEPUBLIKUOTI

Nepublikuoti, jei:
- yra TRUE ABSOLUTE HARD pažeidimas;
- trūksta privalomo SPS RO / SPS UG / savaitgalio coverage;
- kritinis spread >1 ir nėra aiškios diagnostikos, kodėl tai neišvengiama;
- RESIDENT HARD praradimas rodomas be konkretaus paaiškinimo;
- preference, post ar workload statistika nesutampa su pačiu grafiku;
- pageidavimų importas akivaizdžiai nepilnas;
- yra akivaizdus overlap ar kitas feasibility konfliktas.

## 5. Kas nėra automatiškai klaida

- SOFT pageidavimas gali būti neįvykdytas, jei aukštesnio prioriteto fairness / HARD reikalavimai to neleidžia.
- Noncritical posto spread gali laikinai būti iki leidžiamo guardrail, jei tai pagrįstas kompromisas ir sukuriamas POST DEBT ateinančiam mėnesiui.
- Po publikavimo voluntary swapas keičia ACTUAL grafiką, bet neperrašo SYSTEM fairness baseline.
- Ligos / neatvykimo atveju jau dirbantis žmogus gali būti perkeltas iš optional posto į SPS; toks operacinis pull-down yra fairness-neutral.

## 6. Rekomenduojamas visas mėnesio workflow

### 1. Paruošti mėnesį
Patikrinti aktyvų Rule Profile, šventes, etatus / targetus, pozicijų darbo dienas ir administracinius uždarymus.

### 2. Surinkti pageidavimus
Stebėti pateikimo terminą. Seniūnei nereikia ranka perrašyti visų pageidavimų – tik peržiūrėti konfliktinius / neaiškius įrašus.

### 3. Sugeneruoti juodraštį
Pirmiausia leisti solveriui padaryti visą darbą. Nedaryti pusės grafiko ranka prieš generatorių, nes tada prarandamas laiko taupymo tikslas.

### 4. Atlikti trumpą auditą
Naudoti HARD diagnostics, Post Matrix, Resident Stats, Proof ir Išplėstinį preference ledger.

### 5. Taisyti tik išimtis
Jei reali klaida – regeneruoti arba atlikti aiškiai dokumentuojamą korekciją. Jei toolas tik parodo teisėtą SOFT miss, to nereikia „taisyti“ vien dėl 100% skaičiaus.

### 6. Publikuoti
Publikavimas užšaldo SYSTEM fairness baseline. Tai yra oficialus algoritmo sprendinys, su kuriuo vėliau lyginamas ACTUAL grafikas.

### 7. Po publikavimo
Rezidentų swapai turėtų vykti decentralizuotai per platformą. Seniūnė nebeturi būti kiekvieno privataus susitarimo tarpininkė. Liga / neatvykimas tvarkomas repair mechanizmu.

### 8. Mėnesio pabaiga
Peržiūrėti SYSTEM vs ACTUAL, satisfaction pokytį, swapus, repairs ir eksportuoti research datasetą.

## 7. Kaip išmatuoti, ar toolsas iš tikrųjų taupo laiką

Fiksuoti:
- aktyvų generavimo laukimo laiką atskirai nuo aktyvaus žmogaus darbo;
- seniūnės aktyvaus audito laiką;
- kiek konkrečių įrankio teiginių patikrinta;
- kiek patikrintų įrankio teiginių buvo teisingi;
- kiek realių manual corrections prireikė;
- kiek atskirų prisėdimų reikėjo iki publikavimo;
- kiek kontaktų su rezidentais reikėjo;
- kiek post-publication pakeitimų seniūnei teko administruoti pačiai.

Svarbiausias palyginimas nėra „ar teko kažką patikrinti“. Žmogaus kontrolė ir turi likti. Svarbiausias palyginimas:

**rankinis konstravimas + tikrinimas** vs **automatinis konstravimas + kryptingas auditas + išimčių korekcija**.

## 8. Paprastas accountability rodiklis

Galima registruoti:

**Įrankio teiginių tikslumas (claim verification accuracy) = teisingai patvirtintų įrankio teiginių skaičius / visų patikrintų teiginių skaičius.**

Pvz., jei seniūnė patikrino 30 konkrečių HARD / preference / post / weekend teiginių ir 29 sutapo su grafiku, verification accuracy = 96,7%.

Klaida nėra slepiama – ji tampa konkrečiu sistemos kokybės rezultatu ir pataisymo tašku.

## 9. Ką reiškia SYSTEM ir ACTUAL

- **SYSTEM** – tai, ką paskirstė ir publikavo algoritmas. Iš jo skaičiuojama fairness ir mokslinis baseline.
- **ACTUAL** – reali situacija po savanoriškų swapų, ligos, neatvykimų ir operacinių repairs.

Šis atskyrimas leidžia sąžiningai vertinti ir algoritmo kokybę, ir realaus mėnesio dinamiką.

## 10. Esminė taisyklė seniūnei

**Neperdaryti grafiko ranka vien todėl, kad jis atrodo neįprastai. Pirmiausia patikrinti, ką toolas teigia ir kodėl. Jei konkretūs teiginiai teisingi ir guardrailai tenkinami, skirtumas nuo įprasto rankinio grafiko nebūtinai yra klaida.**

## Savanoriškas dublio perėmimas

Jei dublį reikia aktyvuoti žmogui, kuriam tai sukurtų didesnį savaitės krūvį ar 12 val. darbo dieną, Seniūnės lange pirmiausia rodoma pasekmių lentelė: **dabar → po dublio → taikoma riba → būsena**. Jei tai tik perspėjimas, galima atšaukti arba patvirtinti gavus aiškų rezidento sutikimą. Jei lentelė rodo ABSOLUTE / teisinį blokatorių, patvirtinimo mygtukas išjungiamas.

## V2.5.75 — Suvestinė prieš publikavimą

Po `GENERUOTI` seniūnė gali iš karto atverti `Suvestinė`. Kol kandidatas nepaskelbtas, viršuje aiškiai rodoma `JUODRAŠČIO SUVESTINĖ — DAR NEPASKELBTA`. Joje matomi visų rezidentų RESIDENT HARD, `Noriu laisvos`, `Pageidauju dirbti`, bendro išpildymo, workstyle, krūvio, doubles, savaitgalių ir kritinių postų rodikliai bei konkretūs neįvykdyti prašymai. Jei rezultatas netenkina, grįžtama į `Sudarymas` ir kandidatas gerinamas / generuojamas iš naujo. Publikuotas grafikas nesikeičia, kol aiškiai nepaspaudžiama `PASKELBTI / PATVIRTINTI`.
