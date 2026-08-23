# Radiology Scheduler Web V2.5.67 BETA

> **Dabartinis užrakintas checkpointas: V2.5.67 EXACT WORKLOAD + ONKO PAIRS FINAL.**  
> V2.5.65 išlaiko dviejų etapų generatorių (pirma darbo dienos / blokai, po to konkrečios darbo vietos), bet retoms edukacinėms pozicijoms pirmiausia siekia, kad visi tinkami rezidentai gautų bent po vieną ekspoziciją prieš skiriant išvengiamą antrą. Realiame 2026 m. rugsėjo 16 rezidentų regresiniame teste: HARD 0; SPS RO skirtumas 1; SPS UG 1; savaitgaliai 0; Onko RO 1; Centro UG 1; Vaikų UG 1; kiti pagrindiniai postai ≤2; quality gate PASS. Taip pat pridėtos patvirtintos atostogos su proporcingu darbo tikslo mažinimu, aiškesni pageidavimų termino priminimai ir automatiškai atnaujinama privati kelių mėnesių iCalendar prenumerata.

Tai pirmoji bendro naudojimo beta versija su realiomis paskyromis ir Supabase duomenų baze.

Pagrindiniai pakeitimai:

- el. pašto + slaptažodžio prisijungimas;
- vienkartiniai kvietimo kodai, susiejantys paskyrą su konkrečiais inicialais;
- G.M. vienu prisijungimu mato Rezidento ir Seniūnės profilius;
- duomenys saugomi bendroje Supabase/Postgres bazėje, o ne lokaliame `scheduler.db`;
- trumpalaikiai mėnesio ir ilgalaikiai pasikartojantys savaitės dienų pageidavimai;
- `Skaidrumas` vietoj `Skaidrumas / teisingumas` kaip pagrindinis skirtuko pavadinimas;
- pamainomis paremti dubliai iš V2.4.2;
- realiai įvykdytas pavadavimas suteikia kreditus pagal realią trukmę: 6 h = +1 (−1 pamaina), 12 h = +2 (−2 pamainos) pasirinktam būsimam mėnesiui;
- poilsio kreditai automatiškai kitą mėnesį nepritaikomi; V2.5.5 jie galioja 12 mėn.;
- publikavimo laiškai ir priminimai paruošti SMTP siuntimui;
- Supabase Auth gali siųsti paskyros el. pašto patvirtinimą;
- abipusis apsikeitimas beta versijoje galutinai pritaikomas seniūnei atlikus pilną privačių kietų taisyklių patikrą.

Detalūs paleidimo žingsniai: `BETA_SETUP_LT.md`.

## Greitas lokalus paleidimas

```text
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Supabase projekto URL ir publishable key jau yra beta kode kaip saugūs numatytieji viešo kliento parametrai. SMTP slaptažodžių kode nėra.

El. laiškams nukopijuokite `.streamlit/secrets.example.toml` į `.streamlit/secrets.toml` ir įrašykite savo SMTP duomenis. `secrets.toml` nekelkite į GitHub.

Privatūs kvietimo kodai pateikiami atskirai nuo ZIP.


## V2.5.1 BETA — dublio kalendorius ir aktyvavimo pranešimai

- Rezidentas Nustatymuose pasirenka, ar dublio pareigos turi būti įtrauktos į jo `.ics` kalendorių. Pagal nutylėjimą — ne.
- Dubliai vis tiek visada matomi portalo `Dubliai` lange, net jei neįtraukiami į kalendorių.
- Seniūnė gali paspausti `KVIESTI DUBLĮ DABAR`. Tai pažymi konkretų dublį aktyvuotu ir, jei rezidentas įjungęs dublio el. pranešimus, siunčia jam laišką.
- Dublio aktyvavimas pats savaime nesuteikia pavadavimo kredito. Balansas pasikeičia tik tada, kai seniūnė pažymi, kad rezidentas realiai pavadavo.
- Telefono numerio laukas paruoštas būsimam SMS moduliui, tačiau V2.5.1 BETA SMS dar nesiunčia.
- Siunčiančio Gmail / Google Workspace pašto App Password nėra rezidento paskyros duomuo. Tai vienas bendras sistemos secret, kurį administratorius vieną kartą įrašo į Streamlit Secrets. Rezidentai jo nemato ir neįveda.


## V2.5.2 BETA LOCKED
- Dubliai tik savaitgaliais; darbo dienoms jų nėra.
- Istorinis V2.5.2 safety layer turėjo ≤60 žinomų valandų/7 ribą; **V2.5.53 generatoriui ją supersede'ino į ≤48 val./7 d. cap**. V2.5.54 palieka šį cap generatoriui, bet voluntary bilateral normal-shift swapui leidžia sąmoningą >48h išimtį su paveikto rezidento ACK. ≤12 h/d., ≥11 h tarp atskirų darbo dienų, ≤6 darbo dienų/7 ir kiti recovery/HARD lieka privalomi.
- Pateisinamas neatvykimas blokuoja darbą ir proporcingai perskaičiuoja vidinį mėnesio target.
- 38 h/sav. norma nehardcodinta.


## V2.5.4 BETA LOCKED
- V2.5.4 kreditų modelį pakeitė V2.5.5 abipusė tos pačios rūšies POILSIO kredito / DARBO skolos apskaita.
- Dabar pirmakursiams default realus variantas: 1×6 h.
- Senas −3 už vieną pavadavimą modelis panaikintas.


## V2.5.5 BETA LOCKED — abipusis pavadavimų balansas

- Realus pavadavimas keičia **abiejų** rezidentų balansą.
- Pavaduojantis: pirmiausia uždaro seniausią tos pačios rūšies DARBO skolą; jei skolos nėra, gauna POILSIO kreditą.
- Pavaduotas: jei turi laisvą tos pačios rūšies POILSIO kreditą, jis kompensuojamas; kitu atveju atsiranda DARBO skola.
- RYTAS 08–14 = 6 h; POPIETĖ 14–20 = 6 h; NAKTIS 20–08 = 12 h. Rūšys tarpusavyje nekeičiamos.
- Poilsio kreditas galioja 12 mėn.; vienam mėnesiui galima panaudoti max 2 dieninius kreditus.
- Darbo skola: 0–2 mėn. bankuojama, 3–5 mėn. soft prioritetas, 6–11 mėn. strong prioritetas, 12+ mėn. overdue/highest priority. Ji nedingsta, kol realiai neuždaroma.
- Darbo skola užsidaro tik realiai pavadavus tos pačios rūšies pamainą, ne vien nuo standby paskyrimo.
- First-come savarankiškos rezervacijos neliečiamos; skolos prioritetas veikia tik automatiškai skiriamus likusius savaitgalio dublius.


## V2.5.6 BETA LOCKED — fairness hierarchy

- Vertinimo prioritetas: **0 privalomų taisyklių klaidų → Kaupiamasis teisingumas → Mėnesio teisingumas → pageidavimai**.
- Mėnesio teisingumas vertina tik vieną pasirinktą mėnesį.
- Kaupiamasis teisingumas sumuoja visų paskelbtų ankstesnių mėnesių + dabartinio mėnesio savaitgalius, penktadienius, double shifts ir atskiras darbo dienas.
- Formulė abiem vienoda: `100 − 18×weekend spread − 7×Friday spread − 4×double spread − 2×weekday-day spread`.
- `fairness_history` lentelė saugo kiekvieno paskelbto mėnesio faktinius teisingumo komponentus. Patvirtinus normalios pamainos swap, to mėnesio ledger atnaujinamas.
- Transparency lange rodoma hierarchija, abiejų score išskaidymas ir Monthly/Kaupiamasis teisingumas istorijos grafikas.


## V2.5.7 BETA LOCKED — savanoriškas swaps are teisingumo apskaitos nekeičiančiu

- Sistemos teisingumo apskaita = algoritmo paskyrimas paskelbimo momentu.
- Faktinio darbo apskaita = realus grafikas po savanoriškų apsikeitimų.
- Abipusiai patvirtintas savanoriškas normalios pamainos apsikeitimas **nekeičia Monthly ar Kaupiamasis teisingumas**.
- Swap vis tiek keičia faktinį grafiką ir privalo iš naujo praeiti HARD darbo / poilsio / prieinamumo patikrą.
- Fairness istorija po savanoriškas apsikeitimas neperrašoma.
- Vienašaliai / administraciniai perskirstymai nėra automatiškai teisingumo apskaitos nekeičiančiu ir ateityje turi būti žymimi kitu change type.


## V2.5.8 BETA LOCKED — Department Stebėtojas

- Nauja trečia rolė: `observer` / skyriaus administratorės read-only prieiga.
- Stebėtojas turi atskirą vienkartinį invite kodą ir profilį be rezidento inicialų.
- Mato Sistemos pradinis grafikas, ACTUAL grafiką, jų skirtumus, normalių pamainų apsikeitimus, dublių apsikeitimus, dublių būseną ir teisingumo skydą.
- Nemato privačių pageidavimų, privalomo negalėjimo datų, asmeninių pastabų, kontaktų ar individualių kreditų / skolų bankų.
- Stebėtojas neturi jokių write veiksmų UI, o Supabase RLS / privilegijos neleidžia jam rašyti į schedule/swap/fairness/dublis lenteles.
- Abipusiai savanoriškas swaps lieka teisingumo apskaitos nekeičiančiu: observer mato faktinį pokytį, bet SYSTEM FAIRNESS pradinis vertinimas lieka nepakitęs.

## V2.5.9 RESEARCH BETA — Tyrimo langas

- Nauja `Tyrimas` skiltis visiems rezidentams su pradinis vertinimas ir pakartotinis vertinimas anketa.
- R.Š. tyrėjo skydas: deidentifikuoti atsakymai, anoniminiai komentarai, grupės vidurkiai ir pre/post pokytis.
- G.M. skydas: tik agreguoti grupės rezultatai ir anoniminiai komentarai.
- Automatiniai pasirinkto mėnesio operaciniai tyrimo rodikliai: HARD, Monthly/Kaupiamasis teisingumas, pageidavimų išpildymas, sistemos→faktinio grafiko pakeitimai, normalūs/dublis swapai ir realūs pavadavimai.
- Supabase `research_survey_responses` lentelė su RLS; individualus rezidentas gali skaityti tik savo anketą.


## V2.5.11 RESEARCH STUDY BETA — 6 mėn. tyrimo workflow

- Tyrimo laikotarpis: 2026 spalis–2027 kovas.
- Rezidentų anketos tik 3 kartus: pradinis vertinimas (rugsėjis), 3 mėn. (gruodis), 6 mėn. (kovas).
- G.M. turi atskirą grafikų sudarytojos duomenų rinkimą: iškart sudarius grafiką ir pasibaigus mėnesiui.
- R.Š. gauna tyrėjo dashboard su deidentifikuotais eksportais ir 6 mėn. operacinių rodiklių lentele.
- Administratorės read-only profilis gali pateikti tik tyrimo feedback; grafiko redagavimo teisės nesikeičia.
- Kiekvieno generavimo bandymo solver laikas ir sėkmė registruojami automatiškai.


## V2.5.57 — fairness-neutral repair ekspozicija

Jei po publikavimo dėl ligos / atostogų / force majeure rezidentas perkeliamas iš jau suplanuoto optional posto į SPS RO / SPS UG, **ACTUAL grafikas pasikeičia, tačiau fairness apskaita ne**. Summary / Transparency postų spread ir post-debt rodomi iš publikavimo SYSTEM baseline. ACTUAL postų ekspozicija rodoma tik atskirame informaciniame expander'yje ir neįeina į fairness_history, post debt ar ateities catch-up. Tas pats principas taikomas voluntary swapams.


## V2.5.58 setup
Before using the new **Švenčių dienos / Public holidays** setting, run `SUPABASE_MIGRATION_V2_5_58_HOLIDAY_PREFERENCE.sql` once in the Supabase SQL editor. Default is neutral (`0`) for all existing users.

## V2.5.59 — Seniūnės naudojimo ir audito vadovas
Seniūnės profilyje atsirado atskiras skirtukas **Seniūnės vadovas**. Jo paskirtis – padėti naudoti įrankį ne kaip „juodą dėžę“, o kaip audituojamą optimizavimo sistemą: Generate → 5 min. red-flag / claim audit → taisyti tik išimtis → Publish. ZIP taip pat yra atskiras DOCX, kurį galima nusiųsti kitai tvarkaraščio sudarytojai. V2.5.59 naujos Supabase migracijos nereikia.


## V2.5.61 — savanoriškas dublio manual override
Seniūnės Dubliai lange prieš rankinį dublio perėmimą ir aktyvavimą rodoma konkreti pasekmių lentelė. 12 h diena, >40/>48 h 7 dienų krūvis, 6 dienų seka, recovery ar savanoriškas RESIDENT HARD override gali būti patvirtinami tik su aiškiu ACK. ABSOLUTE / operaciniai blokatoriai (overlap, pateisinamas neatvykimas, >12 h/d., <11 h poilsio, >6 d./7 ir aktyvaus Rule Profile maksimali 7 d. riba) lieka neapeinami. Naujos Supabase migracijos nereikia.





## V2.5.66 LOCKED — keli apsikeitimai, bet viena aktyvi užklausa vienai pamainai

- Vienas rezidentas gali turėti kelis vienu metu laukiančius apsikeitimus, jei jie liečia skirtingas pamainas.
- Ta pati konkreti normali pamaina negali būti įtraukta į du aktyvius pasiūlymus vienu metu.
- Ta pati dublio vieta negali būti įtraukta į du laukiančius dublių apsikeitimus.
- Jei antras pasiūlymas bando panaudoti jau rezervuotą pamainą, vartotojas gauna aiškią žinutę, o duomenų bazė transakciniu lygiu blokuoja konfliktą.
- Pasiūlymo autorius gali atšaukti savo dar nepriimtą pasiūlymą.
- Jau pritaikytas arba atmestas swapas neberezervuoja senos pamainos; ją galima vėliau keisti dar kartą pagal dabartinį ACTUAL grafiką.
- Emergency faktiniai pakeitimai lieka atskiras audito srautas ir nėra laikomi konkuruojančiu būsimu pasiūlymu.
- V2.5.65 solverio/fairness logika nepakeista.

## V2.5.65 LOCKED — pirmoji ekspozicija, atostogos ir automatinis kalendorius

- Generatorius pirmiausia sprendžia, **kada** žmogus dirba, o darbo vietas paskirsto antrame etape.
- Jei reto posto mėnesio vietų pakanka bent po vieną kiekvienam tinkamam rezidentui, sistema pirmiausia stengiasi duoti **pirmą ekspoziciją visiems**, o tik tada skiria išvengiamą antrą. Rugsėjo regresijoje Onko RO, Centro UG ir Vaikų UG pasiskirstė su skirtumu 1.
- Patvirtintos `Atostogos` pateikiamos atskirai nuo kitų pageidavimų: tomis dienomis negalima dirbti ar dubliuoti, o mėnesio darbo tikslas proporcingai sumažėja.
- `Nustatymuose` priminimų jungiklis aiškiai nurodo, kad tai yra **pageidavimų pateikimo termino** priminimai, ir rodo konkrečią termino datą.
- `Mano grafikas kalendoriui` turi vienkartinį `.ics` ir privačią prenumeratos nuorodą. Prenumeratos feed'as apima visus paskelbtus mėnesius ir automatiškai atnaujinamas po publikavimo bei svarbių ACTUAL grafiko pakeitimų.
- UI pateikia atskiras nuorodas / instrukcijas Google Calendar, Apple Calendar ir Outlook Calendar; kitoms programoms lieka standartinis `.ics` / iCalendar URL.
- Supabase schemai priklauso trys nuoseklios V2.5.65 migracijos: `SUPABASE_MIGRATION_V2_5_65_VACATION_CALENDAR_FEEDS.sql`, `...65B_AUTO_CALENDAR_FEEDS.sql`, `...65C_CALENDAR_SENIOR_PREPUBLISH.sql`. Dabartiniame beta Supabase projekte jos jau pritaikytos.

## V2.5.64 — count-first fairness engine

- Dviejų fazių architektūra: darbo laikas → konkreti darbo vieta.
- Resident-HARD ir darbo/poilsio taisyklės sprendžiamos prieš postų etiketes.
- SPS RO / SPS UG / savaitgaliai laikomi kuo lygesni; normalus tikslas ≤1.
- Kiti pagrindiniai postai normaliai ≤2; ≤3 leidžiama tik po įrodytos ≤2 neįmanomybės.
- Konkretus SPS paskyrimo laikas nėra laikomas lygybės tikslu pats savaime.
- Realiame rugsėjo regression case generatorius baigė darbą ~14 s vietoje ankstesnio fail-closed timeout.

## V2.5.63 — fairness corridor failsafe

- Tikras darbo vietos skirtumas skaičiuojamas iš faktinių kiekvieno rezidento assignment count reikšmių, o ne iš laisvų pagalbinių solverio max/min kintamųjų.
- SPS RO, SPS UG ir savaitgaliams pirmiausia tikrinamas ≤1 skirtumas. Platesnė riba gali būti svarstoma tik jei siauresnė matematiškai įrodyta neįmanoma; paprastas timeout nėra toks įrodymas.
- Kitiems pagrindiniams postams normalus maksimumas yra ≤2. ≤3 leidžiamas tik po įrodytos ≤2 neįmanomybės.
- Jei fairness paieška baigiasi timeout be patvirtinto tinkamo sprendinio, generavimas baigiasi aiškia žinute ir nelygus SYSTEM grafikas nepateikiamas publikavimui.
- SPS / kitų postų LYGYBĖ saugo mėnesio kiekį, bet konkrečios datos lieka lanksčios. Todėl SOFT laisvadienis gali būti įvykdytas perkeliant lygiavertę pamainą kitam tinkamam rezidentui ar kitai dienai, jei bendras pasiskirstymas išlieka toks pat lygus.
- Naujos Supabase migracijos nereikia.


## V2.5.67 LOCKED — tikslus mėnesio krūvis + Onko poros

- Kiekvieno rezidento apskaičiuotas mėnesio workload targetas yra ABSOLIUTUS: leidžiamas SYSTEM nuokrypis = 0.0.
- Onko 08:00–17:00 = 9 h = 1.5 standartinės 6 h pamainos.
- Todėl individualus Onko skaičius SYSTEM grafike yra lyginis: 0, 2, 4...
- Onko mėnesio spread tarp rezidentų negali viršyti 2.
- Jei vieną mėnesį dalis rezidentų gauna 0, o kiti 2, kitą mėnesį mažiau Onko turintys gauna cumulative catch-up prioritetą.
- Sparse first-exposure logika lieka Centro UG / Vaikų UG ir kitiems 1.0-unit postams, bet nebegali laužyti workload targeto dėl Onko.
- 27.5 / 28.5 / 25.5 SYSTEM workload laikomas HARD ERROR ir negali būti publikuojamas.
