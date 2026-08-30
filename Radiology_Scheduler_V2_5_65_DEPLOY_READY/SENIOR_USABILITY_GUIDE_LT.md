# V2.5.104 — PAGEIDAVIMAMS JAUTRUS WATER-FILL + ONKO-0 → MAMOGRAFIJA

> **Šis skyrius patikslina V2.5.96/V2.5.103 SYSTEM water-fill konstituciją. Jis yra viršesnis ten, kur ankstesni tekstai teigė, kad savaitgalio pageidavimas niekada negali padidinti SYSTEM RAW savaitgalių spread.**

- **Aiškus „Pageidauju dirbti“ savaitgalį yra savanoriškas nepopuliaraus krūvio pasirinkimas.** Jei rezidentas konkrečiai pageidauja šeštadienio / sekmadienio datos (įskaitant ilgalaikį recurring pageidavimą), generatorius stengiasi šį prašymą įvykdyti prieš versdamas neutralų ar nenorintį rezidentą dirbti tą patį nepopuliarų krūvį, jei leidžia ABSOLUTE HARD, poilsis, coverage ir tikslus mėnesio krūvis.
- **Water-fill niekur nedingsta.** Fairness 0–1 taikomas LIKUSIAM NESAVANORIŠKAM šeštadienių, sekmadienių ir savaitgalio SPS RO krūviui. Dėl savanoriškų pageidavimų RAW savaitgalių / SPS RO spread gali būti >1 jau SYSTEM grafike. RAW ekspozicija vis tiek rodoma atskirai.
- **SPS UG lieka struktūrinė kritinė kategorija.** Savanoriško savaitgalio išimtis nekeičia SPS UG raw water-fill.
- **Vienas rezidentas per konkretų šeštadienio+sekmadienio savaitgalį vis tiek gali turėti daugiausia vieną savaitgalio budėjimą.** Savanoriškumas keičia fairness apskaitą, ne fizinio savaitgalio unikalumo taisyklę.
- **Po publikavimo bilateral swapai ir kiti leidžiami ACTUAL pakeitimai gali RAW balansą pakeisti dar labiau.** SYSTEM lieka auditui; jokio kito mėnesio catch-up nėra.
- **Mamografija lieka paskutinio prioriteto neprivalomas kabinetas.** Kai jau nustatyta, kiek Mamografijos slotų apskritai lieka užpildyti po optional-gap pasirinkimo, rezidentams, kurie tą mėnesį turi **0 Onko RO**, pirmiausia stengiamasi duoti bent po vieną likusią Mamografijos ekspoziciją. Tai yra current-month post-breadth prioritetas struktūrinio postų koridoriaus viduje; jis negali pabloginti jau įrodyto postų spread guardrailo.
- V2.5.104 naujos duomenų bazės migracijos nereikia.

# V2.5.100 — EMAIL LIFECYCLE + DURABLE OUTBOX

- Vienas sistemos siuntėjas siunčia operacinius grafiko pranešimus visiems aktyviems rezidentams.
- Etapai: **pageidavimai atidaryti → trūkstamų pageidavimų priminimai → preliminarus grafikas / apsikeitimų etapas → FINAL / baigta**.
- `preferences_open`, `swap_open` ir `final` yra operaciniai etapo pranešimai; individualus `notifications_on` toliau valdo tik periodinius trūkstamų pageidavimų priminimus.
- Kiekvienas lifecycle laiškas prieš SMTP siuntimą įrašomas į `notification_outbox`. Unikalus `event_key + initials` neleidžia Streamlit rerun ar cron jobui netyčia išsiųsti dublikato.
- Nepavykę laiškai lieka retry eilėje. Seniūnė gali pakartoti **tik nepavykusiems**, o background worker gali juos bandyti dar kartą automatiškai.
- Preliminaraus etapo laiškas prisega asmeninį preliminarų `.ics`; FINAL laiškas prisega galutinį `.ics`.
- Automatinis workeris pageidavimų etapą pradeda ankstesnio mėnesio 1 d. 08:00 Lietuvos laiku. Trūkstamų anketų priminimai nuo rezidento pasirinktos `reminder_start_day` dienos siunčiami daugiausia kartą per dieną iki termino.
- Senas atskiras `backup_claim_reminder` lifecycle kelyje nebegeneruojamas, kad žmogus negautų dviejų panašių priminimų tą pačią dieną.
- Seniūnės Simple UI rodo vieną kompaktišką el. pašto paruošimo būseną, kanalo testą ir etapų pristatymo lentelę. SMTP techninė lentelė rodoma tik Išplėstiniame režime.
- Solverio logika V2.5.100 nekeista; `scheduler_engine.py` yra identiškas V2.5.99.

# V2.5.98 dubliai ir kreditai

Privalomas dublio dengimas yra pozicijomis paremtas: SPS RO ir SPS UG visada, Centro UG 120 rytas, Onko RO visa 9 val. pamaina; CENTRO RO best-effort. Realiai pavadavęs rezidentas gauna poilsio kreditą. Pavaduotam žmogui skola nesukuriama.

# V2.5.97 — NAUDOTOJŲ PASTABŲ ATNAUJINIMAS

> **Šis skyrius papildo ir, jei prieštarauja, yra viršesnis už ankstesnius šio dokumento teiginius. V2.5.96 principas „be kito mėnesio fairness catch-up“ lieka galioti.**

- **Centro UG 120 kab. dabar turi RYTĄ ir POPIETĘ.** Naujos PM vietos pridėtos append-only būdu po senų slotų ID, kad ankstesnių paskelbtų grafikų skaitmeniniai slotų ID nepasikeistų.
- **Dengimai / dubliai:** privalomas vardinis dengimas taikomas savaitgalio SPS RO, Centro UG 120 RYTUI, Onko RO pilnai 9 val. dienai, darbo dienos SPS RO RYTUI ir šiuo metu išlaikytam SPS UG dengimui. **CENTRO RO** dengiama kuo plačiau pagal likusią saugią talpą, tačiau jos nepadengimas publikavimo neblokuoja.
- **Mamografija yra paskutinio prioriteto neprivalomas kabinetas.** Kai dėl tikslaus grupės krūvio dalį neprivalomų vietų reikia palikti tuščių, solveris pirmiausia renkasi Mamografijos vietas; kitų kabinetų skylės naudojamos tik kai reikia.
- **Šeštadieniai ir sekmadieniai nuo šiol yra dvi atskiros teisingumo kategorijos.** SYSTEM generavimo metu kiekviena jų water-fill'inama atskirai iki raw spread 0–1. Po publikavimo leidžiami abipusiai swapai / operaciniai pakeitimai gali ACTUAL balansą pakeisti; SYSTEM baseline auditui lieka nekintamas.
- **Darbo dienos trukmės pageidavimas yra tikras aktyvus SOFT signalas.** Sistema pirmiausia nustato neutralų bendrą matematiškai reikalingų AM+PM dvigubų dienų kiekį. Tada, nekeisdama šio bendro kiekio, perskirsto jas pagal aktyvius 6 val. / 12 val. darbo pobūdžio pasirinkimus. Neutralus N/A žmogus nekonkuruoja su aiškiu pageidavimu. Todėl jei tik vienas rezidentas renkasi „dažniausiai 12 val.“, jis turi gauti kuo daugiau jau reikalingų 12 val. dienų, kiek leidžia ABSOLUTE/HARD, poilsis, tikslus mėnesio krūvis ir kritiniai SPS / šeštadienio / sekmadienio guardrailai.
- **Vienodas pageidavimas visai grupei yra atskiras scarcity klausimas.** Galutinė taisyklė, kam pirmiau tenkinti ribotą vienodą pageidavimą, dar neužrakinama V2.5.97 ir bus apibrėžta atskirai.
- **Operacinės nedarbo dienos:** SR (ir ŠR contingency operatorius Išplėstiniame režime) Grafiko lange gali pažymėti `Nedarbingumas`, `Kvalifikacijos kėlimas` arba `Sveikatinimosi diena`. Žyma spalvinama to rezidento spalva, išima jo tos dienos ACTUAL pamainas ir nekeičia SYSTEM baseline. Tiksli priežastis / pastaba rodoma tik lifecycle operatoriui.

# V2.5.96 dabartinė taisyklė

Kiekvienas mėnuo generuojamas nuo švaraus SYSTEM water-fill baseline. Po publikavimo leidžiami override'ai / swapai / repair gali jį pralaužti, o ACTUAL fairness perskaičiuojamas pagal realybę. Istorija yra tik auditui — jokio kito mėnesio catch-up. Completed backup cover fairness ekspoziciją perkelia tik tada, kai realus pavadavimas pažymėtas completed.

# Seniūnės naudojimo ir audito vadovas

## 1. Kam skirtas šis įrankis

Įrankio paskirtis nėra pakeisti seniūnės sprendimą ar reikalauti aklai pasitikėti algoritmu. Jo paskirtis – didžiąją dalį pasikartojančio skaičiavimo, taisyklių derinimo ir fairness kontrolės atlikti automatiškai, o seniūnei palikti **trumpą, kryptingą išimčių auditą**.

Pagrindinis darbo principas:

**Generate → Patikrinti konkrečius teiginius → Taisyti tik išimtis → Publish → Valdyti ACTUAL pakeitimus.**

Seniūnei nereikia dar kartą perskaičiuoti viso mėnesio. Reikia patikrinti, ar keli konkretūs įrankio teiginiai sutampa su pačiu SYSTEM grafiku. **Teiginys** čia reiškia paprastą patikrinamą sakinį, pvz. „18 d. PM prašė laisvos, bet paskirtas SPS UG PM, todėl pageidavimas neįvykdytas.“

## 2. Ką verta patikrinti prieš publikavimą

### A. HARD / diagnostics
- TRUE ABSOLUTE HARD klaidų turi būti 0.
- RESIDENT HARD „Negaliu dirbti“ SYSTEM juodraštyje turi būti **0/0 pažeidimų**. Jei 0-loss grafiko rasti nepavyksta, sistema negrąžina juodraščio, o ne paskiria žmogų jo užblokuotu laiku.
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
- bet koks RESIDENT HARD pažeidimas atsiranda SYSTEM juodraštyje (tai V2.5.107 kritinė klaida);
- preference, post ar workload statistika nesutampa su pačiu grafiku;
- pageidavimų importas akivaizdžiai nepilnas;
- yra akivaizdus overlap ar kitas feasibility konfliktas.

## 5. Kas nėra automatiškai klaida

- SOFT pageidavimas gali būti neįvykdytas, jei aukštesnio prioriteto fairness / HARD reikalavimai to neleidžia.
- Neprivalomo posto skirtumas gali laikinai nukrypti po leidžiamo ACTUAL pakeitimo; tai rodoma gyvoje ACTUAL statistikoje ir nesukuria ateities skolos.
- Po publikavimo voluntary swapas keičia ACTUAL grafiką, bet neperrašo SYSTEM fairness baseline.
- Ligos / neatvykimo atveju jau dirbantis žmogus gali būti perkeltas iš optional posto į SPS; SYSTEM baseline nekinta, tačiau ACTUAL postų/fairness statistika perskaičiuojama pagal realų darbą.

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


### V2.5.79 ONE-WAY EMERGENCY RESCUE
 EMERGENCY RESCUE


Senas pavadinimas „Emergency swap“ buvo misnomer. Naujas modelis yra vienpusis operational rescue:

1. Pats realiai perkeltas rezidentas savo paskyroje pasirenka `CURRENT LOCATION`.
2. Pasirenka to paties laiko kritinį `MOVING TO` postą (SPS RO / SPS UG).
3. Sistema spalvotai parodo `RESCUED PERSON` — žmogų, kuris tuo metu buvo kritiniame poste.
4. Patvirtinus:
   - mover pašalinamas iš seno žemesnio prioriteto optional posto;
   - jo `CURRENT LOCATION` lieka **tuščias**;
   - mover įrašomas į `MOVING TO` kritinį postą;
   - `RESCUED PERSON` atleidžiamas nuo target posto;
   - rescued person **nėra** perkeliamas į mover seną vietą.

Tai keičia ACTUAL operational grafiką ir ACTUAL fairness statistiką. SYSTEM publication baseline lieka užšaldytas auditui; post debt / future catch-up V2.5.96 nebenaudojamas. Nauji rescue įrašai žurnale rodomi `CURRENT LOCATION → MOVING TO` formatu, su spalvotais mover / rescued inicialais. Seni `emergency_actual` bilateraliniai įrašai paliekami tik kaip aiškiai pažymėtas LEGACY auditas.

## V2.5.107 greita patikra po GENERUOTI

Po generavimo `Sudarymas` turi rodyti keturis skaičius: **Aktyvūs pageidavimai**, **Įvykdyta**, **Neįvykdyta**, **Negaliu dirbti pažeidimai**. Paskutinis skaičius SYSTEM juodraštyje privalo būti **0**. Jei `Neįvykdyta = 0`, turi būti matoma žalia žinutė **„VISI AKTYVŪS PAGEIDAVIMAI ĮVYKDYTI“**. Jei `Neįvykdyta > 0`, prieš publikavimą peržiūrėkite šalia esančią **NEĮVYKDYTI PAGEIDAVIMAI** lentelę.

### V2.5.109 — grafiko eksportas
Sudaryme ir Grafiko tvirtinime nebereikia naudotis vien tik lentelės viršuje esančiu CSV eksportu. Po grafiku visada yra atskiri **Excel (.xlsx)** ir **CSV (.csv)** mygtukai. Excel galima atsisiųsti iš karto po generavimo, prieš FINAL, iš ACTUAL būsenos ir po FINAL patvirtinimo.

