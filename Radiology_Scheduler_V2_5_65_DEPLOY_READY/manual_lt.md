# DABARTINĖ OPERACINĖ POLITIKA — V2.5.112

> Ši V2.5.112 politika yra viršesnė už žemiau likusias istorines versijų pastabas: `Negaliu dirbti` = 0 pažeidimų; savaitgaliai skirstomi ADMIN RAW water-fill principu ir jų negalima „nusipirkti“ pageidavimu; SP+ŠR+GE Dream Team siekiama kartu CENTRO RO kartą per savaitę; AUTO dubliai/pavadavimai water-fill'inami automatiškai; savanoriškas swapas keičia ACTUAL tik po abiejų rezidentų sutikimo ir SP galutinio APPROVE.

# V2.5.112 — ADMIN WATER-FILL + DREAM TEAM + AUTO DUBLIAI + SP GATE + WESTON

- **SYSTEM savaitgaliai nebėra rezidento pasirinkimas.** Konkretus „Pageidauju dirbti“ šeštadienį / sekmadienį ir senas savaitgalio krypties nustatymas negali nupirkti papildomo savaitgalio krūvio. Generatorius pirmiausia ieško **mažiausio matematiškai įmanomo RAW šeštadienių, sekmadienių ir bendro savaitgalio spread**, saugodamas 0 „Negaliu dirbti“ pažeidimų, saugą, coverage ir tikslų krūvį.
- Jei 0–1 neįmanoma, engine **neapsimeta**, kad lygybė pasiekta: tikrina 1 → 2 → 3 → 4 ir užrakina pirmą įmanomą koridorių. Po publikavimo savanoriški swapai gali pakeisti ACTUAL balansą, bet SYSTEM baseline nekeičiamas.
- **Dream Team SP + ŠR + GE** prioritetiškai statomi kartu į **CENTRO RO bent vieną AM arba PM bloką kiekvieną atstovaujamą kalendorinę savaitę**, jei tai nepažeidžia aukštesnių HARD taisyklių. Rodomas pasiektas savaičių skaičius.
- **AUTO dubliai / pavadavimai sukuriami kartu su GENERUOTI paspaudimu**, todėl jie iš karto matomi juodraščio statistikoje, Excel „Dubliai“ lape ir asmeniniame grafike. Privalomi: SPS RO, SPS UG, Centro UG 120 rytas ir Onko RO. CENTRO RO naudojamas tik kaip best-effort fairness filler: keliami mažesnį backup krūvį turintys žmonės iki privalomų dublių viršutinio sluoksnio, bet optional dubliai negali sukurti naujos nelygybės.
- Rezidento dublio claim yra tik tie-break lygiame sluoksnyje; jis negali aplenkti backup water-fill. Dublis niekada neplanuojamas per „Negaliu dirbti“ bloką.
- **Swapas ACTUAL pritaikomas tik po 3 žingsnių:** iniciatorius → kitas rezidentas sutinka → **SP galutinai APPROVE / DECLINE**. SP mato visus normalius ir dublių swapus. Swapai gali sąmoningai pralaužti SYSTEM fairness; tai lieka matoma kaip ACTUAL pokytis.
- **WESTON:** kiekvienas SP paspaudimas `GENERUOTI / PERKURTI` = +1 WESTON beer. Skaitiklis saugomas DB ir rodomas SP statistikoje.

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

# V2.5.98 — POZICIJOMIS PAREMTI DUBLIAI + TIK KREDITAS

- Dublio prievolė siejama su darbo vieta, ne su savaitgaliu: **SPS RO ir SPS UG dengiami visada**, Centro UG 120 — rytas, Onko RO — visa 9 val. pamaina. CENTRO RO dengiamas best-effort.
- Dabartiniai šeštadienio ir sekmadienio budėjimai yra SPS RO, todėl automatiškai patenka į privalomą SPS RO dengimą. Ateityje atsiradę SPS RO / SPS UG naktiniai slotai paveldės tą pačią taisyklę.
- Realus pavadavimas sukuria **tik poilsio kreditą pavaduojančiam rezidentui**. Pavaduotam žmogui jokia darbo skola nesukuriama ir jo turimi kreditai neatimami.
- RYTO ir POPIETĖS kreditai gali mažinti būsimo pasirinkto mėnesio dieninį targetą; bendra panaudojimo riba lieka 2 dieniniai kreditai per mėnesį.

# V2.5.97 — NAUDOTOJŲ PASTABŲ ATNAUJINIMAS

> **Šis skyrius papildo ir, jei prieštarauja, yra viršesnis už ankstesnius šio dokumento teiginius. V2.5.96 principas „be kito mėnesio fairness catch-up“ lieka galioti.**

- **Centro UG 120 kab. dabar turi RYTĄ ir POPIETĘ.** Naujos PM vietos pridėtos append-only būdu po senų slotų ID, kad ankstesnių paskelbtų grafikų skaitmeniniai slotų ID nepasikeistų.
- **Dengimai / dubliai:** privalomas vardinis dengimas taikomas savaitgalio SPS RO, Centro UG 120 RYTUI, Onko RO pilnai 9 val. dienai, darbo dienos SPS RO RYTUI ir šiuo metu išlaikytam SPS UG dengimui. **CENTRO RO** dengiama kuo plačiau pagal likusią saugią talpą, tačiau jos nepadengimas publikavimo neblokuoja.
- **Mamografija yra paskutinio prioriteto neprivalomas kabinetas.** Kai dėl tikslaus grupės krūvio dalį neprivalomų vietų reikia palikti tuščių, solveris pirmiausia renkasi Mamografijos vietas; kitų kabinetų skylės naudojamos tik kai reikia.
- **Šeštadieniai ir sekmadieniai nuo šiol yra dvi atskiros teisingumo kategorijos.** SYSTEM generavimo metu kiekviena jų water-fill'inama atskirai iki raw spread 0–1. Po publikavimo leidžiami abipusiai swapai / operaciniai pakeitimai gali ACTUAL balansą pakeisti; SYSTEM baseline auditui lieka nekintamas.
- **Darbo dienos trukmės pageidavimas yra tikras aktyvus SOFT signalas.** Sistema pirmiausia nustato neutralų bendrą matematiškai reikalingų AM+PM dvigubų dienų kiekį. Tada, nekeisdama šio bendro kiekio, perskirsto jas pagal aktyvius 6 val. / 12 val. darbo pobūdžio pasirinkimus. Neutralus N/A žmogus nekonkuruoja su aiškiu pageidavimu. Todėl jei tik vienas rezidentas renkasi „dažniausiai 12 val.“, jis turi gauti kuo daugiau jau reikalingų 12 val. dienų, kiek leidžia ABSOLUTE/HARD, poilsis, tikslus mėnesio krūvis ir kritiniai SPS / šeštadienio / sekmadienio guardrailai.
- **Vienodas pageidavimas visai grupei yra atskiras scarcity klausimas.** Galutinė taisyklė, kam pirmiau tenkinti ribotą vienodą pageidavimą, dar neužrakinama V2.5.97 ir bus apibrėžta atskirai.
- **Operacinės nedarbo dienos:** SP (ir ŠR contingency operatorius Išplėstiniame režime) Grafiko lange gali pažymėti `Nedarbingumas`, `Kvalifikacijos kėlimas` arba `Sveikatinimosi diena`. Žyma spalvinama to rezidento spalva, išima jo tos dienos ACTUAL pamainas ir nekeičia SYSTEM baseline. Tiksli priežastis / pastaba rodoma tik lifecycle operatoriui.

# V2.5.96 — DABARTINĖ FAIRNESS KONSTITUCIJA: MONTHLY BASELINE + LIVE ACTUAL, BE CATCH-UP

> **Šis skyrius yra viršesnis už visus ankstesnius manualo / README teiginius apie fairness-neutral swapus, post debt, cumulative catch-up ar ankstesnių mėnesių kompensavimą.**

- **Kiekvienas naujas mėnuo prasideda nuo švaraus SYSTEM water-fill baseline.** Ankstesnių mėnesių savaitgalių, penktadienių, dublių, darbo dienų, postų ekspozicijų, švenčių ar RESIDENT-HARD nuostolių istorija **nėra solverio input** ir nesukuria kompensacinės skolos.
- **Jei niekas nieko nekeičia po generavimo, gaunamas neutralus water-fill grafikas.** Individualūs SOFT pageidavimai optimizuojami baseline fairness ribose; jie negali nupirkti platesnio SYSTEM water-fill koridoriaus.
- **Po publikavimo manual override, abipusis swapas, emergency repair ir kiti leidžiami ACTUAL pakeitimai gali sulaužyti water-fill.** Tai leidžiama, jei praeina išliekantys ABSOLUTE / fizinio įmanomumo / darbo-laiko blokatoriai ir kitos neapeinamos taisyklės.
- **SYSTEM baseline lieka nekintamas auditui ir tyrimui. ACTUAL fairness yra gyva realybės statistika.** Po kiekvieno pakeitimo ACTUAL postų ekspozicija ir mėnesiniai spread perskaičiuojami pagal tai, kas realiai turi pamainas dabar.
- **Completed backup cover** perkelia konkretaus covered slot ACTUAL ekspoziciją realiai pavadavusiam žmogui. Vien suplanuotas ar aktyvuotas standby be `completed_at` ACTUAL fairness nekeičia.
- **Istoriją saugome tik stebėjimui / auditui.** Galima matyti SYSTEM ir ACTUAL skirtumą kiekvieną mėnesį ir trendą, tačiau istorija **niekada negrįžta į kito mėnesio solverį kaip catch-up**.
- **Post debt / future fairness catch-up išjungtas.** Rule Profile laukas paliktas tik schemos suderinamumui ir V2.5.96 engine jo nenaudoja.
- **Per mėnesio ribą išlieka tik saugos / spacing kontekstas**, pvz. realiai dirbtų iš eilės savaitgalių tail ir paskutinės dienos Onko būsena. Tai nėra fairness kompensacija.

# Grafiko taisyklės

Šis dokumentas aprašo rezidentų mėnesinio grafiko sudarymo, paskelbimo, pavadavimų ir pakeitimų tvarką. Sistemos tikslas – vienodai taikyti kietas taisykles, skaidriai paskirstyti krūvį ir kuo geriau išpildyti individualius pageidavimus.

## 1. Vartotojų vaidmenys

Kiekvienas žmogus turi atskirą paskyrą su el. paštu ir slaptažodžiu. Pirmos registracijos metu paskyra susiejama su konkrečia rezidento tapatybe naudojant vienkartinį kvietimo kodą. Viena paskyra gali būti susieta tik su vienu rezidentu. **SP** yra operacinė Seniūnė. **ŠR** turi rezidento / tyrėjo paskyrą ir Išplėstiniame režime gali naudoti kontingencines lifecycle administravimo funkcijas; kitų rezidentų paskyros yra rezidento-only.

### Rezidento profilis

Rezidentas gali:

- pildyti ir keisti tik savo mėnesio pageidavimus;
- keisti savo darbo pobūdžio ir pranešimų nustatymus;
- matyti paskelbtą grafiką, suvestines ir teisingumo rodiklius;
- matyti savo dublių / pavadavimų grafiką;
- atsisiųsti savo kalendorių;
- siūlyti ir priimti savanoriškus apsikeitimus;
- savo patikros lange matyti, kurie pageidavimai išpildyti, o kurie ne.

Rezidentas negali generuoti, perkurti ar tiesiogiai redaguoti oficialaus grafiko.

### Seniūnės profilis

Seniūnė turi visas rezidento funkcijas ir papildomai gali:

- matyti visų rezidentų pateiktus pageidavimus ir jų apimtį;
- matyti, kas dar neužpildė pageidavimų arba nenurodė el. pašto;
- generuoti ir perkurti grafiko juodraštį;
- paskelbti ir užrakinti oficialią grafiko versiją;
- redaguoti taisyklių dokumentą;
- valdyti dublių / pavadavimų lentelę;
- įvesti faktinį pavadavimą, jeigu realybėje pavadavo ne planuotas žmogus;
- inicijuoti priminimų siuntimą, kai naudojamas el. pašto modulis.

## 2. Pageidavimų pateikimo terminas

Kito mėnesio pageidavimai pateikiami **iki einamojo mėnesio 13 dienos imtinai**.

Sistema kiekviename profilyje rodo:

- tikslią pasirinkto mėnesio pageidavimų pateikimo datą;
- kiek dienų liko iki termino;
- ar terminas jau praėjo.

Terminas yra bendras visai grupei.

## 3. Paskyra, el. paštas ir pranešimai

Kiekvieno rezidento paskyroje turi būti nurodytas el. pašto adresas.

Pranešimai pagal nutylėjimą yra **įjungti**. Nustatymuose rezidentas gali juos išjungti arba pasirinkti, nuo kurios mėnesio dienos pradėti gauti priminimus apie artėjantį 13 dienos terminą.

Kol kito mėnesio pageidavimai nepateikti, priminime nurodoma, kiek dienų liko iki termino.

Patvirtinus ir užrakinus grafiką, sistema paruošia pranešimą visiems grupės nariams, kad kito mėnesio grafikas patvirtintas. Kai sukonfigūruotas el. pašto siuntimas, laiške siunčiamas ir asmeninis `.ics` failas, kurį galima pridėti prie kalendoriaus.

## 4. Nustatymai, trumpalaikiai ir ilgalaikiai pageidavimai

### Nustatymai

Nustatymai aprašo įprastą žmogaus darbo pobūdį ir galioja tol, kol pats žmogus juos pakeičia: darbo dienų kryptis, savaitgalių kryptis, grafiko išsklaidymas / sutelkimas, pageidaujama 6/12 val. darbo dienos trukmė, pranešimai, priminimų pradžios diena ir el. paštas. Jie automatiškai taikomi visiems būsimiems dar neužšaldytiems mėnesiams ir nėra pildomi iš naujo kas mėnesį.

### Trumpalaikiai mėnesio pageidavimai

Konkrečiam mėnesiui galima pažymėti:

- **Negaliu dirbti** – privaloma taisyklė visai dienai, rytui arba popietei;
- **Noriu laisvos** – minkštas pageidavimas konkrečioms datoms;
- **Pageidauju dirbti** – pageidavimas konkrečioms datoms. Jei pasirinkta penktadienio ar savaitgalio data, tai yra SOFT savanoriškas pasirinkimas. Penktadienio pageidavimas vykdomas tik jei kartu išlaikomas SYSTEM penktadienių structural water-fill raw spread 0–1; po publikavimo abipusis ACTUAL swapas gali šį balansą pakeisti;
- kiek RYTO ir / arba POPIETĖS poilsio kreditų norima panaudoti tam mėnesiui (bendra riba – 2 dieniniai kreditai per mėnesį);
- papildomą komentarą.

### Ilgalaikiai pasikartojantys pageidavimai

Jeigu žmogus reguliariai turi tą patį savaitinį režimą, galima nustatyti taisyklę pagal **savaitės dienos pavadinimą**, o ne konkrečią mėnesio datą. Pavyzdžiui: kiekvieną antradienį pageidauju dirbti, kiekvieną ketvirtadienį noriu laisvos arba kiekvieną pirmadienio rytą tikrai negaliu dirbti.

Ilgalaikė taisyklė automatiškai pritaikoma kiekvienam naujam mėnesiui, kol žmogus ją pakeičia arba išjungia. Ji redaguojama tame pačiame **Pageidavimų** lange po konkretaus mėnesio forma. Konkretaus mėnesio minkštas pageidavimas turi pirmenybę prieš priešingą ilgalaikį minkštą pageidavimą. Ilgalaikė **kieta** taisyklė išlieka kieta ir negali būti apeita vien mėnesio minkštu pageidavimu.

## 5. Taisyklių prioritetas

Sistema sprendimus priima tokia tvarka:

1. **Kietos taisyklės** – negali būti pažeistos.
2. **Teisingumas** – krūvis ir nepatogios pamainos paskirstomi kuo tolygiau.
3. **Minkšti pageidavimai** – tenkinami tiek, kiek leidžia pirmi du lygiai.
4. **Kosmetinis optimizavimas** – grafikas daromas patogesnis ir įvairesnis.

Jeigu kietų taisyklių suderinti neįmanoma, sistema grafiko nesukuria.

## 6. Mėnesio krūvis

Bazinis mėnesio pamainų tikslas:

**darbo dienų skaičius × 7,6 / 6**

Rezultatas apvalinamas iki artimiausio sveiko skaičiaus.

Oficialūs vaidmens koregavimai taikomi po bazinio skaičiavimo. Dabartinėje konfigūracijoje seniūnės krūvis mažinamas 2 pamainomis.

Viena **Onko RO centre** diena verta 1,5 pamainos. Vienam žmogui Onko paskyrimų skaičius turi būti lyginis.

## 7. Kietos taisyklės

Kietos taisyklės niekada neaukojamos dėl pageidavimo ar teisingumo rodiklio.

### Kietas negalėjimas dirbti

Rezidentas gali pažymėti:

- **visą dieną** – tą dieną negali gauti jokios normalios pamainos ir negali būti dublis;
- **tik rytą (08:00–14:00)** – negali gauti rytinės ar pilnos dienos pamainos ir negali dubliuoti rytinės ar pilnos dienos pamainos;
- **tik popietę (14:00–20:00)** – negali gauti popietinės ar pilnos dienos pamainos ir negali dubliuoti popietinės ar pilnos dienos pamainos.

Jeigu pažymėtas tik vienas pusdienis, kitu nesikertančiu pusdieniu žmogus gali dirbti arba būti dublis.

Kitos privalomos taisyklės:

- Vienam žmogui per dieną – daugiausia 2 normalios grafiko pamainos.
- Negali persidengti dvi rytinės ar dvi popietinės pamainos.
- Pilnos dienos pamaina negali persidengti su kita normalia pamaina.
- Privalomi SPS RO d.d. ir SPS UG 1035 kab. postai turi būti padengti.
- Savaitgalio SPS budėjimai turi būti visiškai padengti.
- Vieną savaitgalį dirba 4 skirtingi žmonės: 2 šeštadienį ir 2 kiti sekmadienį.
- Vienas žmogus per konkretų savaitgalį gali turėti daugiausia 1 savaitgalio pamainą.
- Mamografijos 31 kab. popietė penktadieniais visada blokuota.
- Mėnesio krūvio tikslas turi būti tikslus.
- Onko paskyrimų skaičius žmogui turi būti lyginis.
- **Kiekviena užpildyta normalaus grafiko pamaina privalo turėti konkretų dublį**, kuris tuo pačiu laiko bloku yra laisvas ir neturi kieto negalėjimo dirbti.

Jeigu mėnesio darbo dienų skaičius lyginis, Onko pildomas kiekvieną darbo dieną. Jeigu nelyginis, leidžiama viena neužpildyta Onko diena.


## 8. Dvigubos pamainos ir nuovargis

**Dviguba pamaina** reiškia dvi suderinamas normalias pamainas tą pačią dieną. Tai nėra tas pats, kas dublis / pavadavimas.

Dviguba pamaina leidžiama tik tada, kai nesikerta laikas. Sistema papildomai baudžia ilgą darbą iš eilės ir nepageidaujamus dublius, todėl, esant alternatyvai, didesnis krūvis stumiamas į labiau pailsėjusio žmogaus dieną.

## 9. Dubliai / pavadavimai

**Dublis** yra konkretus rezidentas, paskirtas pavaduoti **konkrečią normalaus grafiko pamainą**, jeigu prireiktų.

Dubliai generuojami **pagal pamainas**, o ne pagal visą dieną.

Pavyzdžiui, jei SA tą pačią dieną dirba:

- Centro RO 08:00–14:00;
- SPS UG 14:00–20:00,

rytinę ir popietinę pamainą gali dubliuoti du skirtingi žmonės. Tas pats žmogus gali dubliuoti abi tik tada, jeigu abiem laiko blokais yra tinkamas.

### Kas gali būti dublis konkrečiai pamainai

Kandidatas gali būti dublis, jeigu:

1. tuo pačiu laiko bloku neturi persidengiančios normalios pamainos;
2. tuo laiku nėra pažymėjęs kieto negalėjimo dirbti;
3. nėra pats dubliuojamos pamainos darbuotojas.

Todėl žmogus, kuris pats dirba tik popietę, gali būti rytinės pamainos dublis. Ir atvirkščiai.

Pilnos dienos pamainai dublis turi būti laisvas visą su ja persidengiantį laiką.

### Pilnas padengimas

Kiekviena užpildyta normalaus grafiko pamaina turi turėti **vieną planuotą dublį**. Jeigu bent vienai pamainai nėra nė vieno tinkamo kandidato, grafiko negalima laikyti pilnai paruoštu ir jo paskelbimas blokuojamas.

Jeigu tinkamų dublių yra mažiau nei vienu metu dubliuojamų pamainų, tas pats žmogus gali būti priskirtas kelioms pamainoms. Sistema pirmiausia stengiasi mažinti vienalaikį kartojimą, po to balansuoti bendrą mėnesio dublių skaičių ir vengti nuolatinių tų pačių porų.

### Vaizdavimas ir kalendorius

Rezidento Dubliai lange ir `.ics` kalendoriuje matoma:

- konkreti data;
- konkretus laiko blokas;
- žmogus, kurį dubliuoja;
- konkretus padalinys / pamaina.

Kalendoriaus įvykis turi tokį pat laiką kaip dubliuojama pamaina, todėl žmogus iš karto mato, kuriuo pusdieniu yra dublis.

### Faktinis pavadavimas

Jeigu realybėje pavadavo kitas žmogus, seniūnė gali įvesti **faktinį dublį**. Faktinis žmogus taip pat turi būti tinkamas konkrečiam laiko blokui. Dublių statistikoje ir galiojančiame vaizde tada naudojamas faktinis, o ne planuotas dublis.

Po patvirtinto savanoriško apsikeitimo dubliai perskaičiuojami pagal naują galiojantį normalų grafiką.


### Realus pavadavimas: poilsio kreditas

Planuotas ar tik aktyvuotas dublis kredito nesukuria. Kai seniūnė pažymi, kad rezidentas **realiai pavadavo**, pavaduojantis rezidentas gauna vieną tos konkrečios rūšies poilsio kreditą. Pavaduotam žmogui **jokia skola nesukuriama** ir jo jau turimi kreditai dėl šio įvykio neatimami.

- **RYTAS** = 08:00–14:00, 6 val.
- **POPIETĖ** = 14:00–20:00, 6 val.
- **NAKTIS** = 20:00–08:00, 12 val. (kai sistemoje atsiras naktiniai slotai).
- Kreditas galioja 12 mėnesių nuo realaus pavadavimo datos.
- RYTO ir POPIETĖS kreditas po 1 vienetą gali sumažinti pasirinkto būsimo mėnesio dieninį targetą; per mėnesį galima panaudoti daugiausia 2 dieninius kreditus iš viso.
- NAKTIES kreditai kol kas kaupiami atskirai ir dabartinio PGY1 dieninio targeto nemažina.
- Klaidingai pažymėtą realų pavadavimą seniūnė gali atšaukti, jei iš jo gautas kreditas dar nepanaudotas.

## 10. Fairness: kaip jį suprasti

Fairness **niekada nėra aukščiau už kietas taisykles**. V2.5.6 grafikas vertinamas tokia hierarchija:

| Lygis | Ką sistema tikrina | Kaip interpretuoti |
|---|---|---|
| **1. Privalomų taisyklių atitiktis** | Teisinės, fizinės, prieinamumo ir poilsio saugos taisyklės | **Privaloma 0 klaidų.** Jei yra bent viena privalomos taisyklės klaida, grafiko skelbti negalima. |
| **2. Savanoriškas nepopuliarus darbas** | Aiškiai pageidautą penktadienio ar savaitgalio darbo datą | **„Savanoriškas pageidavimas dirbti penktadienį vykdomas tik structural Friday raw spread 0–1 viduje; savaitgalio pageidavimas taip pat negali pralaužti aukštesnių SYSTEM struktūrinių taisyklių.“** |
| **3. Kaupiamasis teisingumas** | Sistemos paskirtą nesavanorišką nepopuliarų krūvį per mėnesius | SYSTEM penktadienių struktūrinėje taisyklėje skaičiuojami VISI užpildyti penktadienio priskyrimai, net jei data buvo pageidauta. Po publikavimo savanoriški ACTUAL swapai SYSTEM istorijos neperrašo. |
| **4. Mėnesio teisingumas** | Pasirinkto mėnesio sistemos paskirtą krūvį | Einamojo mėnesio balansas tvarkomas po savanoriškų nepopuliarių pasirinkimų. |
| **5. Kiti pageidavimai** | Likusius individualius norus | Tenkinami maksimaliai, kai aukštesni lygiai leidžia. |
| **4. Soft preferences / kosmetika** | Asmeninius norus, darbo stilių, išsklaidymą ir pan. | Optimizuojama tik tada, kai aukštesni lygiai leidžia. |

### Kodėl rodomi du fairness procentai

**Mėnesio teisingumas** atsako į klausimą:

> „Ar šį konkretų mėnesį nepatogesnės darbo charakteristikos pasiskirstė kuo lygiau?“

**Kaupiamasis teisingumas** atsako į svarbesnį klausimą:

> „Ar per visą sistemos naudojimo laiką vieni rezidentai sistemingai negauna daugiau nepatogių pamainų už kitus?“

Pavyzdžiui, jeigu A per ankstesnius mėnesius turėjo mažiau savaitgalių nei B, kitą mėnesį A gali gauti vienu savaitgaliu daugiau. Tokio mėnesio **Mėnesio teisingumas gali būti mažesnis**, tačiau **Kaupiamasis teisingumas pagerėja**. Tai laikoma teisingu sistemos elgesiu.

### Formulė

Abu procentai naudoja tą pačią formulę:

**Fairness = 100 − 18 × savaitgalių spread − 7 × penktadienių spread − 4 × double-shift spread − 2 × darbo dienų spread**

Jeigu rezultatas mažesnis nei 0, rodoma 0%.

**Spread** reiškia `didžiausia reikšmė − mažiausia reikšmė` tarp visų rezidentų.

| Komponentas | Bauda už 1 spread vienetą | Kodėl svarbu |
|---|---:|---|
| Savaitgaliai | **−18** | Didžiausia fairness svarba, nes savaitgalio darbas labiausiai veikia laisvalaikį |
| Penktadieniai | **−7** | Nepatogesnė savaitės pabaigos našta |
| Double shifts | **−4** | 12 val. darbo dienos / labiau koncentruotas krūvis |
| Atskiros darbo dienos | **−2** | Kiek dienų per mėnesį žmogus turi atvykti į darbą |

Monthly score šiuos keturis spread skaičiuoja **tik iš pasirinkto mėnesio**.

Cumulative score kiekvienam rezidentui pirmiausia sumuoja visų **anksčiau paskelbtų mėnesių + pasirinkto mėnesio** savaitgalius, penktadienius, double shifts ir darbo dienas, ir tik tada apskaičiuoja spread.

V2.5.6 cumulative apskaita yra tikra visiems keturiems komponentams. Ankstesnėse beta versijose tik savaitgaliai turėjo cumulative carry-in, o kiti komponentai buvo mėnesiniai.

### Ką reiškia 92%

92% **nereiškia, kad grafikas yra 92% „teisingas“ ar 8% blogas**. Tai techninis grupės lygybės indikatorius pagal aukščiau aprašytus keturis komponentus.

Pavyzdžiui:

- savaitgalių spread = 0;
- penktadienių spread = 0;
- double-shift spread = 2;
- darbo dienų spread = 0.

Tuomet:

**100 − 4 × 2 = 92%**

Tai reiškia tik tai, kad daugiausiai ir mažiausiai double pamainų gavusių žmonių skirtumas yra 2.

### Kodėl 100% ne visada įmanoma

**100% reiškia spread = 0 visuose keturiuose komponentuose.** Tai ypač viename mėnesyje dažnai matematiškai neįmanoma.

Priežastys:

- pamainų skaičius gali nesidalinti iš 16 rezidentų;
- mėnuo turi nevienodą penktadienių ir savaitgalių skaičių;
- kai kurios pamainos turi specifines coverage taisykles;
- yra privalomų negalėjimų dirbti;
- skiriasi individualūs targetai ir pateisinami neatvykimai;
- cumulative sistema kartais sąmoningai taiso ankstesnių mėnesių skirtumus.

Todėl rezultatą reikia skaityti tokia tvarka:

**0 privalomų taisyklių klaidų → savanoriškai pasirinktas nepopuliarus darbas → Kaupiamasis teisingumas → Mėnesio teisingumas → kiti pageidavimai.**

### Fairness istorijos grafikas

`Skaidrumas / Transparency` lange sistema rodo dvi linijas per mėnesius:

- **Kaupiamasis teisingumas** – ar bendra grupės našta ilgainiui lygiuojasi;
- **Mėnesio teisingumas** – kiek lygus buvo kiekvienas atskiras mėnuo.

Idealus ilgalaikis elgesys nebūtinai reiškia, kad Monthly linija kiekvieną mėnesį yra 100%. Svarbiau, kad Cumulative linija būtų aukšta ir sistema neleistų ilgalaikiam skirtumui sistemingai augti.

### SYSTEM FAIRNESS vs ACTUAL darbas

V2.5.7 aiškiai atskiria du ledgerius:

- **Sistemos teisingumo apskaita** – ką rezidentui paskyrė pats algoritmas paskelbimo momentu;
- **Faktinio darbo apskaita** – ką rezidentas faktiškai dirba po savanoriškų apsikeitimų.

Jei A ir B **abu savanoriškai sutinka** apsikeisti pamainomis, apsikeitimas yra **teisingumo apskaitos nekeičiančiu**.

Pavyzdys: sistema A paskyrė penktadienį, B – antradienį. A ir B tarpusavyje susitaria apsikeisti. Faktiniame grafike penktadienį dirba B, tačiau fairness apskaitoje penktadienio našta lieka A, nes tai buvo sistemos pradinis paskyrimas. B neturi gauti papildomos cumulative „baudos“ už pamainą, kurią pats savanoriškai priėmė.

Todėl abipusis apsikeitimas:
- **nekeičia Mėnesio teisingumas**;
- **nekeičia Kaupiamasis teisingumas**;
- nekeičia ateities algoritminės kompensacijos;
- tačiau pakeičia ACTUAL grafiką, kalendorių, darbo laiko / poilsio privalomų taisyklių patikrą ir kitą faktinio darbo auditą.

Ši taisyklė saugo nuo „dirbtinio spreado“: žmonės gali tarpusavyje optimizuoti grafiką pagal asmeninį patogumą, o sistema vėliau jų už tai nebaudžia.

Svarbi išimtis: jei pakeitimas nėra tikras abipusis savanoriškas trade – pvz., seniūnė / administracija vienašališkai perskirsto pamainą, žmogus neatvyksta ir darbo našta priverstinai perkeliama kitam ar atliekama sisteminė korekcija – toks įvykis nėra automatiškai teisingumo apskaitos nekeičiančiu. Tokius pakeitimus ateityje reikia žymėti kaip atskirą **administracinio perskirstymo** tipą, kuris gali koreguoti teisingumo apskaita.

Paskelbimo momento Sistemos teisingumo apskaita lieka audituojamas ir yra naudojamas kitų mėnesių kaupiamajam balansavimui.

## 11. Asmeninis pageidavimų išpildymas

Kiekvienam žmogui skaičiuojamas atskiras pageidavimų išpildymo procentas tik iš tų kategorijų, kuriose jis išreiškė norą.

Vertinamos aktyvios kategorijos:

- pageidaujamos darbo dienos;
- norėtos laisvos dienos;
- darbo dienų kryptis;
- savaitgalių kryptis;
- pamainų išsklaidymas / sutelkimas;
- dvigubų pamainų vengimas.

Neutralus **0 / nesvarbu** į procentą neįtraukiamas.

Skaidrumo lange kartu rodomi:

- grupės **kaupiamasis teisingumas** procentas;
- žmogaus asmeninis pageidavimų išpildymo procentas paskelbimo momentu;
- dabartinis asmeninis procentas po savanoriškų pakeitimų;
- asmeninio pageidavimų išpildymo ir grupės kaupiamasis teisingumas balanso santykis.

Balanso santykis skaičiuojamas kaip mažesnis iš dviejų procentų, padalytas iš didesnio. **1,00** reiškia, kad asmeninis ir grupinis rodikliai yra vienodo lygio. Šis santykis neparodo absoliučios kokybės, todėl visada vertinamas kartu su abiem procentais.

## 12. Asmeninė patikra

Paskelbus grafiką kiekvienas rezidentas turi atskirą **Patikros** langą.

Jame sistema vizualiai, lentelėmis, būsenomis ir procentinėmis juostomis parodo:

- ar išlaikytos kietos nedarbo dienos;
- kurios norėtos laisvos dienos suteiktos ir kurios ne;
- kurios pageidautos darbo dienos pataikytos ir kurios ne;
- ar darbo dienų, savaitgalių, išsklaidymo ir dvigubų pamainų pobūdis atitiko pasirinktus nustatymus;
- ar išlaikytas tikslus mėnesio krūvis;
- sisteminį rezultatą paskelbimo momentu ir dabartinį rezultatą po savanoriškų pakeitimų.

Neatitikimai pažymimi aiškiai; Patikros lange nerodomas programinis kodas, tik galutiniai žmogui suprantami rezultatai. Jei privaloma taisyklė nepažeista, bet minkštas pageidavimas neišpildytas, rezidentas gali ieškoti savanoriško sprendimo per apsikeitimų sistemą.

## 13. Grafiko paskelbimas

Seniūnė pirmiausia generuoja **juodraštį**. Juodraštį galima perkurti tol, kol jis nepaskelbtas.

Tik seniūnė gali pasirinkti **Paskelbti ir užrakinti**. Paskelbimo momentu išsaugoma pradinė bazinė versija ir jos teisingumo statistika.

Po paskelbimo oficialus grafikas keičiamas tik kontroliuojamais pakeitimais.

## 14. Apsikeitimai

V2.5 beta bendroje Supabase versijoje abu rezidentai vis dar turi savanoriškai sutikti su apsikeitimu. Kadangi galutinė kietų taisyklių patikra naudoja visos grupės privačius prieinamumo duomenis, beta versijoje po abipusio sutikimo seniūnė paspaudžia galutinį pritaikymą. Seniūnė negali viena inicijuoti apsikeitimo už du žmones; ji tik paleidžia galutinę patikrą ir, jei ji sėkminga, sistema pritaiko apsikeitimą ir perskaičiuoja dublius.


Po paskelbimo rezidentas gali pasiūlyti konkrečią savo pamainą keisti į konkrečią kito žmogaus pamainą.

1. Pirmas žmogus pateikia pasiūlymą.
2. Antras žmogus priima arba atmeta.
3. Priėmus sistema iš naujo patikrina visas kietas taisykles.
4. Tik sėkmingai praėjus patikrą pakeitimas įsigalioja.
5. Pradinė užrakinta grafiko versija lieka išsaugota.
6. Savanoriškas apsikeitimas neperskaičiuoja ir nemažina paskelbimo momentu užfiksuoto bendro teisingumo procento.

## 15. Skaidrumas

Visi grupės nariai mato:

- kietų taisyklių patikros rezultatą;
- paskelbimo momentu užfiksuotą bendrą teisingumo rodiklį;
- sukauptų savaitgalių, penktadienių, dvigubų pamainų ir darbo dienų skirtumus;
- individualius pageidavimų išpildymo rodiklius;
- asmeninio ir grupinio rodiklio santykį;
- norėtų laisvų dienų išpildymą;
- ilgiausią iš eilės dirbtų dienų seriją.

## 16. Nuolatinės spalvos

Kiekvienas grupės narys turi vieną fiksuotą spalvą. Ji nesikeičia tarp mėnesių ir naudojama grafike, suvestinėse, apsikeitimuose, dublių lange bei eksporte.

## 17. Eksportas

Galima atsisiųsti:

- asmeninį `.ics` failą su normaliomis pamainomis ir dublių / pavadavimų įvykiais;
- spalvotą `.xlsx` mėnesio grafiką su padaliniais eilutėse, dienomis stulpeliuose, nuolatinėmis žmonių spalvomis ir suvestine.

## 18. Kalba

Sąsaja turi du atskirus režimus:

- **LT** – visa naudotojui rodoma informacija lietuviškai;
- **EN** – visa naudotojui rodoma informacija angliškai.

Kalbos viename režime nemaišomos.


## Darbo teisės ir poilsio saugos taisyklės — V2.5.2

Šis modulis yra kietas saugos sluoksnis, o ne individualios darbo sutarties ar įstaigos darbo laiko apskaitos pakaitalas.

- Rytas 08:00–14:00 ir Popietė 14:00–20:00 tą pačią dieną gali būti skiriami tam pačiam žmogui: tai 12 val. darbo diena. 11 val. poilsio taisyklė taikoma tarp atskirų darbo dienų / pamainų, o ne tarp dviejų 6 val. tos pačios darbo dienos dalių.
- Šiame grafike darbo diena negali viršyti 12 val.
- Tarp atskirų darbo dienų turi likti bent 11 val. nepertraukiamo poilsio. Esant dabartiniams laikams, Popietė 20:00 → kitos dienos Rytas 08:00 palieka 12 val.
- Per bet kurias 7 paeiliui einančias kalendorines dienas galima dirbti ne daugiau kaip 6 dienas.
- **Generuojant / regeneruojant** per bet kurias 7 paeiliui einančias dienas šiame grafike žinomas darbo laikas negali viršyti **48 val.**; generatorius papildomai taikosi į maždaug **40 val./7 d.** ir savaitinį krūvį water-fill'ina tarp rezidentų. Po publikavimo yra viena siaura išimtis: abipusis savanoriškas normalių pamainų swapas gali padidinti paveikto rezidento rolling-7 maksimumą virš 48 val. tik po aiškaus jo ACK.
- Viena pilna laisva kalendorinė diena, esant dabartinėms 08:00–20:00 riboms, sukuria mažiausiai 36 val. nepertraukiamo poilsio tarp ankstesnės dienos 20:00 ir po laisvos dienos sekančios 08:00 pradžios; tai konservatyviai saugo bent 35 val. savaitinį poilsį.
- Jei pažymima realaus >12–24 val. arba 24 val. budėjimo **pradžios data**, visa sekanti kalendorinė diena blokuojama normalioms pamainoms kaip konservatyvi bent 24 val. poilsio apsauga.
- `Pateisinamas neatvykimas` (liga, atostogos ar kita patvirtinta priežastis) yra kieta nedarbo data. Sistema tą dieną neskiria pamainų ir proporcingai perskaičiuoja vidinį mėnesio pamainų tikslą, kad neatvykimas nebūtų automatiškai „atsidirbamas“.
- **38 val./sav. sutartinė norma V2.5.2 nėra hardcodinta.** FTE, suminės apskaitos laikotarpis ir konkrečios sutarties normos bus atnaujinamos vėliau.
- Programoje 48 val. riba yra **generatoriaus saugos guardrail**, o ne teisinės konsultacijos pakaitalas. V2.5.54 voluntary normal-shift swapui leidžia ją peržengti tik su aiškiu paveikto rezidento sutikimu; šis sutikimas neatlaisvina kitų programos saugos taisyklių.
- Sistema tikrina tik jai žinomą darbo laiką. Jei žmogus dirba kitoje darbovietėje ir tas laikas nesuvestas, programos poilsio / 48 val. per 7 d. patikra negali būti laikoma pilna visų darboviečių teisine patikra.

Teisinis pagrindas: Lietuvos Respublikos darbo kodekso 114 straipsnio maksimaliojo darbo laiko ir 122 straipsnio minimaliojo poilsio principai bei Valstybinės darbo inspekcijos oficiali informacija apie maksimalų darbo laiką ir minimalų poilsio laiką. Prieš naudojant kaip galutinę teisinę kontrolę būtina suderinti su faktiniu Klinikų / LSMU darbo laiko režimu, kolektyvine sutartimi ir apskaitos tvarka.

## Dubliai — V2.5.98 AKTYVI TAISYKLĖ

Privalomas dublio dengimas yra **pozicijomis paremtas**: SPS RO ir SPS UG — visada, Centro UG 120 — rytas, Onko RO — visa 9 val. pamaina. CENTRO RO dengiamas kuo plačiau best-effort, tačiau jo trūkumas publikavimo neblokuoja. Generic „savaitgalio dublio“ taisyklės nebėra: dabartinis savaitgalis dengiamas todėl, kad visos savaitgalio budėjimo pamainos yra SPS RO.

## Dublių savitarna — V2.5.98

Rezidentai gali iš anksto rezervuoti privalomus dublio slotus iš galimų pozicijų. Rezervacija visada tikrinama pagal persidengimą, ABSOLUTE HARD ir RESIDENT HARD logiką. Neužimti privalomi slotai paskirstomi automatiškai kuo tolygiau; jokios darbo skolos ar skolos prioriteto eilės nėra.

## Skyriaus administratorės / stebėtojo READ-ONLY paskyra — V2.5.8 LOCKED

Skyriaus administracijai sukurtas atskiras **Department Stebėtojas / Skyriaus stebėtojo** vaidmuo. Tai nėra seniūnės paskyra ir ji neturi jokių grafiko valdymo teisių.

Stebėtojas gali matyti:

- **Sistemos pradinis grafikas** grafiką — originalų algoritmo paskirstymą paskelbimo momentu;
- **ACTUAL** grafiką — dabartinį galiojantį grafiką po abipusių savanoriškų apsikeitimų;
- aiškią lentelę, kurios normalios pamainos pasikeitė tarp pradinis vertinimas ir actual;
- visų normalių pamainų apsikeitimų būsenas ir istoriją;
- visų savaitgalio dublių apsikeitimų būsenas ir istoriją;
- savaitgalio dublių lentelę: kas buvo planuotas dublis, faktinis dublis, ar dublis aktyvuotas ir ar realiai pavadavo;
- Privalomų taisyklių atitiktis, Mėnesio teisingumas, Kaupiamasis teisingumas ir fairness komponentų išskaidymą;
- fairness istorijos grafiką per mėnesius;
- aktualų Manual / taisykles.

### Ko stebėtojas NEGALI daryti

READ-ONLY paskyroje nėra ir duomenų bazės teisėmis neleidžiama:

- generuoti juodraščio;
- publikuoti grafiko;
- tvirtinti ar atmesti apsikeitimų;
- atlikti senior final-apply;
- keisti normalių pamainų ar dublių;
- aktyvuoti dublio;
- pažymėti realaus pavadavimo;
- keisti fairness istorijos;
- redaguoti Manual;
- keisti rezidentų profilių ar rolės.

### Privatumo ribos

Skyriaus stebėtojui sąmoningai **nerodomi**:

- individualūs rezidentų pageidavimai;
- HARD negalėjimo dirbti datos;
- pateisinamų neatvykimų detalės;
- asmeninės rezidentų pastabos;
- el. pašto adresai ir notification nustatymai;
- slaptažodžiai / kvietimo kodai;
- individualus poilsio kreditų bankas.

Stebėtojas mato tik tiek asmens duomenų, kiek būtina operacinei grafiko priežiūrai: vardą / inicialus, paskirtas ir aktualias pamainas, su pamainomis susijusius apsikeitimus ir dublio faktą.

### Sistemos pradinis grafikas ir Faktinis grafikas

Šis vaidmuo ypač svarbus todėl, kad po paskelbimo skyriaus administracija neturi remtis vien sena PDF / Excel kopija.

Portale vienu metu matomi du vaizdai:

1. **Sistemos pradinis grafikas** — kas buvo oficialiai sugeneruota ir paskelbta.
2. **ACTUAL** — kas realiai galioja dabar po patvirtintų apsikeitimų.

Abipusis savanoriškas apsikeitimas išlieka **teisingumo apskaitos nekeičiančiu**: Faktinis grafikas pasikeičia, tačiau Sistemos teisingumo apskaita neperrašomas. Todėl stebėtojas gali matyti ir realią operacinę situaciją, ir originalų sistemos teisingumo paskirstymą jų nesumaišydamas.

Stebėtojo paskyra aktyvuojama atskiru vienkartiniu invite kodu ir po aktyvavimo portale visada aiškiai rodoma **READ ONLY** būsena.

## Tyrimo langas (V2.5.9 RESEARCH BETA)

Visi rezidentai turi **Tyrimas** skiltį, kurioje gali užpildyti trumpą bazinę („Prieš naudojimą“) arba vėlesnę („Po naudojimo“) anketą. Tie patys pagrindiniai 1–5 balų klausimai kartojami abiejuose etapuose, kad vėliau būtų galima skaičiuoti pokytį.

ŠR ir SP turi papildomą tyrimo skydą. SP mato grupės lygio operacinius rodiklius ir agreguotas anketų suvestines; ŠR tyrėjo paskyra papildomai turi tyrimo kokybės kontrolės ir eksporto funkcijas.

Privatumas: SP mato tik grupės agreguotus anketų rezultatus ir anoniminius komentarus. ŠR tyrėjo vaizde papildomai prieinami deidentifikuoti individualūs įrašai su pseudoniminiu kodu; šiame lange rezidentų vardai ir inicialai prie atsakymų nerodomi. Tyrimo duomenys saugomi atskiroje lentelėje nuo grafiko pageidavimų.

Ši anketa yra projekto v0.1 instrumentas, o ne galutinai validuota psichometrinė skalė. Prieš formalų publikavimą klausimynas ir tyrimo protokolas turi būti metodologiškai peržiūrėti ir, jei reikia, suderinti su etikos / IRB tvarka.


---

## V2.5.11 — naudotojo srauto ir terminijos patobulinimai

- Lietuviškame režime vartotojui rodomi lietuviški terminai: **privalomos taisyklės**, **pageidavimai**, **mėnesio teisingumas**, **kaupiamasis teisingumas**, **faktinis grafikas**, **apsikeitimas**.
- Meniu punktas **„Tyrimas“** pervadintas į **„Anketa“**.
- Išsaugojus svarbiausius rezidento pageidavimus ar nustatymus rodoma aiški žalia **✓ Išsaugota** būsena.
- **Darbo teisės / poilsio saugos duomenys** perkelti į mėnesio pageidavimų apačią, prieš seniūnės „Visų rezidentų pageidavimai“ dalį.
- Laukas **„Jau žinomo ilgo budėjimo už šio grafiko ribų pradžios data“** skirtas tik iš anksto žinomam budėjimui, kurio ši schedulerio sistema pati neplanuoja. Po tokio įrašo sistema kitą dieną blokuoja įprastoms pamainoms kaip 24 val. poilsio apsaugą.
- Kai ateityje pati schedulerio sistema skirs ilgą / naktinį LSMU budėjimą, tas budėjimas turi automatiškai patekti į tą patį privalomą poilsio mechanizmą — rezidentui jo ranka kartoti nereikės.
- Dublių kreditai rodomi atskiroje kreditų dalyje; darbo skolų modelis nebenaudojamas.
- Anketos kontroliniuose taškuose naudojamos trys aiškios būsenos: **Neužpildyta**, **Dar neaktyvuota**, **✓ Užpildyta**.

### Dar likęs V2.5.11 darbas

Po realiai aktyvuoto budėjimo numatytas atskiras **„Prašyti pakeitimo po budėjimo“** srautas su tinkamų savanorių pasiūlymais ir el. laišku „Prašau perimti pamainą“. Šio srauto šiame greitame testiniame pakete dar neprijungėme prie Supabase / el. pašto mechanizmo, kad prieš naktinį testą nekeistume stabilios apsikeitimų logikos.


## UŽTVIRTINTA FAIRNESS TAISYKLĖ — DARBO VIETŲ / MODALITETŲ ĮVAIROVĖ

Kiekvieną mėnesį sistema turi stengtis, kad kiekvienas rezidentas pabūtų kuo daugiau skirtingų darbo vietų:
CENTRO RO, Onko RO, SPS RO, Centro UG, SPS UG, ADC 144, ADC 145, Vaikų UG ir Mamografijos.

Tai yra pagrindinis ilgalaikio fairness principas, tačiau ne absoliuti HARD feasibility sąlyga. HARD saugumas,
DK / poilsio taisyklės, neprieinamumas ir darbo valandų targetai visada yra aukščiau. Jei konkrečiame mėnesyje
dėl šių apribojimų ar realaus pamainų skaičiaus vienodo darbo vietų paskirstymo pasiekti neįmanoma, sistema
neturi laikyti grafiko klaidingu. Ji turi išsaugoti paskelbto SYSTEM grafiko ekspozicijų istoriją ir per
artimiausias tinkamas pamainas bei kitą mėnesį prioritetiškai mažinti susidariusį skirtumą.

Kiekviena darbo vieta balansuojama tarp rezidentų atskirai. Pvz., Mamografijos kiekiai lyginami tarp rezidentų,
bet nėra reikalavimo, kad Mamografijos kiekis būtų toks pats kaip CENTRO RO kiekis. Mėnesio tikslas taip pat yra
maksimizuoti skirtingų darbo vietų skaičių vienam rezidentui ir vengti bereikalingo to paties rezidento
kartojimo toje pačioje vietoje, kai egzistuoja lygiavertis validus paskirstymas.



## UŽTVIRTINTA V2.5.21 TAISYKLĖ — MĖNESIO POSTŲ LYGYBĖ PIRMA

Pagrindinis postų fairness tikslas yra kiekviename pasirinktame mėnesyje kiekvieną postą paskirstyti tarp rezidentų kuo lygiau.
Kiekvienam postui atskirai minimizuojamas šio mėnesio spread = didžiausias pamainų skaičius tame poste minus mažiausias pamainų skaičius tame poste.
Idealus spread yra 0; jei pamainų skaičius nesidalina tolygiai ar egzistuoja realūs apribojimai, mažiausias pasiekiamas spread dažniausiai yra 1 ar kitas matematiškai neišvengiamas dydis.

Tik tada, kai dėl HARD taisyklių, darbo valandų, availability ar realios pamainų pasiūlos mėnesio postų lygybės pilnai pasiekti neįmanoma, likęs skirtumas persikelia į kaupiamąją SYSTEM istoriją ir ateinančiomis pamainomis / kitą mėnesį sistema prioritetiškai bando jį ištaisyti.

Trumpai: MONTHLY POST EQUALITY FIRST → CUMULATIVE CATCH-UP SECOND.



## LOCKED V2.5.28 — GENERATORIAUS BAZINĖ FILOSOFIJA

**Normalize inputs → satisfy HARD → establish fairness-optimal space → optimize true SOFT within that space → maximize diversity → use cumulative history as catch-up → keep best valid solution found.**

1. Prieš solverį individualūs SOFT pageidavimai normalizuojami ir nedubliuojami su jau veikiančiomis HARD arba globaliomis engine taisyklėmis.
2. HARD taisyklės yra absoliučios.
3. Dabartinio mėnesio fairness sudaro pagrindinę gero grafiko erdvę: postų spread, workload, weekendai, Fridays, doubles, consecutive-days/fatigue ir kiti bendri fairness kriterijai vertinami kaip sistemos taisyklės.
4. N/A = 0 pageidavimo svorio ir veikia kaip lanksti talpa.
5. Tikri individualūs SOFT optimizuojami gero fairness erdvėje; jų tenkinimas neturi neproporcingai sugadinti visos grupės fairness.
6. Tarp panašiai gerų variantų didinama darbo vietų / modalitetų įvairovė.
7. Cumulative SYSTEM istorija yra antrinis catch-up tik tam disbalansui, kurio dabartiniame mėnesyje išvengti nepavyko.
8. Generatorius saugo geriausią rastą HARD-valid kandidatą. Timeout nėra lygu „grafikas neįmanomas“.
9. Kai visi N/A, sistema turi beveik visą optimizavimo galią skirti fairness ir pateikti stiprų pirmą juodraštį.

Ši filosofija yra **FROZEN BASELINE** ir nekeičiama be aiškaus sprendimo keisti optimizerio taisykles.



## LOCKED V2.5.29 — TAISYKLĖS = ENGINE

Jokia taisyklė negali egzistuoti tik aprašyme. Jei taisyklė rodoma sistemoje, ją turi vykdyti engine arba aiškiai vykdyti kitas sistemos mechanizmas.

Generatoriaus seka:
**Preference normalization → HARD feasibility → global fairness/fatigue baseline → real fairness guardrails → true individual SOFT guardrail erdvėje → diversity/cumulative tie-breakers → best valid solution.**

Fairness guardrail mechanika:
- kiekvieno posto šio mėnesio spread po SOFT optimizavimo negali būti blogesnis už fairness-only baseline;
- weekend, weekday workload, Friday, double ir weekday-day mėnesio spread gali pablogėti daugiausia +1, kad SOFT turėtų ribotą manevro laisvę;
- šios ribos yra realios solverio constraints, ne tik display score;
- jei SOFT etapas nespėja, paliekamas fairness baseline;
- jei fairness etapas nespėja, paliekamas HARD-valid fallback;
- timeout nėra automatiškai laikomas infeasible.



## LOCKED V2.5.32 — DUBLIŲ PADENGIMO APIMTIS

Vardinį dublį privalo turėti:
- visos savaitgalio pamainos;
- visos darbo dienų **SPS RO d.d.** pamainos;
- visos darbo dienų **SPS UG 1035** AM ir PM pamainos.

Rezidentas iki pasirinkimo termino gali rezervuoti kelis konkrečius šių grupių dublio slotus. Rezervuotas dublio slotas yra realus generatoriaus inputas: tuo pačiu laiko bloku tam rezidentui negali būti paskirta persidengianti normali pamaina. Tas pats konkretus covered slot gali turėti tik vieną self-claim. Nepasirinkti privalomi dubliai paskirstomi automatiškai, laikantis HARD prieinamumo, normalių pamainų nepersidengimo ir dublių krūvio balansavimo.

Ši taisyklė vykdoma engine, DB rezervacijų sluoksnyje, publikavimo patikroje ir Dubliai / pavadavimai UI.


## V2.5.50 — dviejų dimensijų pageidavimų teisingumas

Pageidavimai optimizuojami dviem kryptimis. **Vertikaliai** galioja griežtas prioritetas: ABSOLUTE HARD → RESIDENT HARD → SOFT-1 → SOFT-2 → SOFT-3. Aukštesnio rango rezultatas užrakinamas prieš pereinant žemyn.

| Rangas | Kas įeina | Principas |
|---|---|---|
| ABSOLUTE HARD | Darbo teisė, poilsio sauga, patvirtinta liga/atostogos, fizinis neįmanomumas | 100 % privaloma; niekada nelaužoma |
| RESIDENT HARD | „Negaliu dirbti“ — data, AM, PM, pasikartojantis | **0 pažeidimų privaloma.** Tai SYSTEM generavimo draudimas; fairness ir SOFT optimizuojami tik likusioje 0-loss erdvėje. Jei tokio grafiko nėra, juodraštis negrąžinamas. |
| SOFT-1 | „Noriu laisvos“, struktūruotas dublių / atsistatymo vengimas | Pirmiausia saugomas asmeninis laikas ir poilsis |
| SOFT-2 | „Pageidauju dirbti“ — konkreti data / AM / PM | Teigiamas paskyrimas į norimą laiką |
| SOFT-3 | Ilgalaikis darbo pobūdis | Darbo dienų / savaitgalių kryptis, išsklaidymas / koncentracija ir kiti darbo stiliaus signalai. **Generuojant SYSTEM**, savaitgalio kryptis gali tik parinkti viršutinį / apatinį sluoksnį jau užrakintame šeštadienio ir sekmadienio water-fill koridoriuje; vien šis SOFT pasirinkimas jo nepraplečia. **Po publikavimo** abipusiai savanoriški swapai gali pakeisti ACTUAL šeštadienio / sekmadienio pasiskirstymą ir padidinti spread; SYSTEM baseline dėl to neperrašomas ir kito mėnesio catch-up nekuriamas. |

**Horizontaliai** kiekviename range veikia progressive-filling / water-filling principas. Jei rezidentų pageidavimų kiekiai yra `2,2,2,4`, sistema pirmiausia siekia `2,2,2,2`, o tik tada bando įvykdyti likusius du ketvirto rezidento pageidavimus. Jei kiekiai `2,2,3,4`, pirmas bendras sluoksnis yra `2,2,2,2`, o likę `0,0,1,2` optimizuojami tik po to. Taigi didesnis įvestų pageidavimų kiekis nesuteikia didesnės balsavimo galios.

Kiekviename SOFT range pirmiausia maksimalizuojamas blogiausiai aptarnauto rezidento įvykdytų pageidavimų kiekis, po to bendras įvykdymas, o likę lygiaverčiai sprendiniai palenkiami mažesnio išsibarstymo naudai. Jei papildomas pageidavimas gali būti įvykdytas nepabloginant aukštesnio rango ar jau užrakinto bendro sluoksnio, jis nėra švaistomas — sistema jį įvykdo.

## V2.5.52 — istorinis fairness etapas

Šio seno etapo cumulative/post-debt kompensavimo dalis **nebenaudojama**. Nuo V2.5.96 kiekvienas mėnuo prasideda nuo švaraus SYSTEM water-fill baseline, o ankstesnių mėnesių istorija yra tik auditui ir tyrimui.

## V2.5.53 — savaitinio krūvio ir recovery water-filling

V2.5.53 įveda atskirą **temporal workload** matricą: rezidentas × savaitė / slenkantis 7 dienų langas. Tikslas — kad tikslus mėnesio krūvis nebūtų sugrūstas į vieną savaitę vienam žmogui, pvz., 60 val. pirmą savaitę, kai kiti tuo metu dirba gerokai mažiau.

| Sluoksnis | Taisyklė | Statusas |
|---|---|---|
| Rolling 7 dienos | Ne daugiau kaip **48 žinomos darbo valandos** | TRUE ABSOLUTE HARD; Rule Profile gali tik sugriežtinti |
| Rolling 7 dienos | Ne daugiau kaip **6 darbo dienos** — bent 1 visiškai laisva diena | TRUE ABSOLUTE HARD |
| Weekly target | Generatorius pirmiausia mažina blogiausią viršijimą virš **~40 val./7 d.**, tada bendrą viršijimą ir kalendorinės savaitės krūvio spread tarp rezidentų | STRUCTURAL WATER-FILL |
| Po 1 dvigubos 12 val. dienos | Kitą dieną kita dviguba pamaina stipriai vengiama; viena pamaina arba poilsis yra geriau | STRUCTURAL RECOVERY |
| Po 2 dvigubų 12 val. dienų iš eilės | Kitą dieną leidžiama tik **PM arba visiškai laisva**; laisva diena preferinama | HARD RECOVERY + structural preference |
| 3 dvigubos dienos iš eilės | Neįmanomos dėl ankstesnės taisyklės | HARD |

Savaitinis krūvis water-fill'inamas **horizontaliai tarp rezidentų**: toje pačioje kalendorinėje savaitėje sistema minimizuoja valandų max–min spread, o slenkančiuose 7 dienų languose pirmiausia mažina blogiausiai apkrautą žmogų. Tai yra analogiška kitoms water-filling taisyklėms: papildomas krūvio sluoksnis neturi kristi tam pačiam žmogui, kol egzistuoja lygiavertė galimybė jį paskirstyti kitiems.

Šis sluoksnis „compilinamas“ su kitais užraktais: TRUE ABSOLUTE HARD → **RESIDENT HARD 0-loss** → kritinis SPS RO/SPS UG/savaitgalių fairness (0–1 tikslas, leidžiama sertifikuota struktūrinė išimtis prieš pažeidžiant „Negaliu dirbti“) → kritinis spacing → **weekly load/recovery water-fill** → kitas burden fairness → ordinary-post guardrails → SOFT → post debt. Todėl vėlesnis SOFT pageidavimas negali vėl sukurti 60 val. savaitės, panaikinti privalomos laisvos dienos ar sukurti trijų 12 val. dienų sekos.


## V2.5.54 — savanoriško normalių pamainų swapo >48 val. ACK

- Generatorius ir regeneravimas **niekada neplanuoja >48 žinomų valandų per slenkančias 7 dienas** ir toliau taikosi į ~40 val./7 d.
- Po publikavimo **tik bilateral savanoriškam normalių pamainų swapui** galima viršyti 48 val. ribą.
- Prieš siunčiant / priimant swapą sistema dry-run būdu perskaičiuoja FAKTINĮ grafiką. Jei būtent šis swapas padidina rezidento rolling-7 maksimumą virš 48 val., jam parodomas prognozuojamas maksimalus valandų skaičius ir konkretūs slenkantys 7 d. langai.
- Rezidentas turi pažymėti aiškų sutikimą. Jei abu rezidentai dėl to paties swapo patirtų naują >48h maksimumą, **abu turi sutikti atskirai**.
- Sutikimas saugomas ACTUAL swapo audite kartu su rezidentu, swap ID ir patvirtintu rolling-7 valandų cap.
- Sutikimas yra tik **48 val. ribos** išimtis. Jis **neleidžia** apeiti ≤12 h/d., minimalaus poilsio, ≤6 darbo dienų/7 d., recovery po dviejų double, patvirtinto neatvykimo, overlap/coverage/eligibility ar naujo RESIDENT-HARD konflikto draudimo.
- Repair / administraciniams priverstiniams pakeitimams ši voluntary ACK išimtis netaikoma.
- SYSTEM fairness baseline lieka užšaldytas; po swapo perskaičiuojamas ACTUAL request satisfaction ir savaitinio krūvio diagnostika.

## V2.5.57 — neplanuotas neatvykimas, kritinių SPS postų gelbėjimas ir fairness-neutral ekspozicija

Po publikavimo liga, atostogos, kitas pateisinamas neatvykimas ar force majeure keičia tik **FAKTINĮ (ACTUAL)** grafiką. Paskelbimo momento SYSTEM grafikas ir jo fairness istorija neperrašomi.

Jei neatvykstantis rezidentas buvo paskirtas į **SPS RO arba SPS UG**, kritinis postas turi išlikti padengtas. Sistema taiko tokią operacinę hierarchiją:

1. Pirmiausia ieškomas rezidentas, kuris tą pačią dieną ir persidengiančiu laiko bloku jau dirba **žemesnės hierarchijos neprivalomame poste** (pvz. CENTRO RO, Centro UG, ADC, Vaikų UG, Mamografija).
2. Toks rezidentas perkeliamas į kritinį SPS postą, o jo optional donorinis postas gali likti tuščias.
3. Kritinis SPS postas niekada nenaudojamas kaip donorinis postas kitai mažesnio prioriteto vietai.
4. Onko automatiškai nenaudojamas kaip donorinis postas, nes turi atskirą mėnesio coverage taisyklę.
5. Jei nėra nė vieno saugaus tos pačios pamainos optional donorinio perkėlimo, tik tada galima naudoti tame laiko bloke laisvo rezidento fallback.
6. Tarp kelių to paties bloko donorų pirmiausia vengiama naujų RESIDENT HARD konfliktų. **Postų spread, post debt ir ankstesnis pull-down skaičius donorų pasirinkimui nelaikomi fairness kriterijais**, nes žmogus jau buvo suplanuotas dirbti tą patį laiką; keičiasi tik jo darbo vieta.

### Fairness-neutral apskaitos taisyklė

Emergency pull-down gali sukurti papildomą optional gap ACTUAL grafike. Tai leidžiama todėl, kad privalomas SPS coverage yra aukštesnis operacinis prioritetas. Tačiau tokio pakeitimo negalima vėliau interpretuoti kaip algoritmo nelygybės:

- **SYSTEM fairness** lieka toks, koks buvo publikavimo momentu;
- **SYSTEM postų spread** skaičiuojamas iš publikavimo baseline, ne iš po ligos pakeisto ACTUAL grafiko;
- **post debt / future catch-up** nuo repair nesikeičia;
- **weekend / double / burden fairness_history** nuo repair nesikeičia;
- rezidentui, kuris jau buvo darbe ir buvo perkeltas iš Centro RO / ADC / kito optional posto į SPS, nepridedamas „papildomas fairness vienetas“ už SPS;
- ACTUAL ekspozicija gali būti rodoma atskiroje informacinėje lentelėje, kad būtų žinoma, kur žmogus realiai dirbo, tačiau ji aiškiai pažymima **NE FAIRNESS**.

Taigi publikavimo SYSTEM matrica atsako į klausimą „ką paskirstė algoritmas?“, o ACTUAL operacinė matrica — „kur žmonės realiai dirbo po swapų / ligų / force majeure?“. Tyrimo ir ilgalaikio fairness vertinimui naudojama pirmoji.


## V2.5.58 — Švenčių dienų paskirstymas

Nustatymuose kiekvienas rezidentas gali pasirinkti vieną ilgalaikį SOFT signalą: **norėčiau dirbti per šventes**, **neutralu**, arba **norėčiau ilsėtis per šventes**. Tai nėra teisė pasiimti visas šventes ar jų visų išvengti.

Oficialioms Lietuvos švenčių dienoms sistema taiko atskirą preference-cohort water-filling. Aukštesni ABSOLUTE HARD, SPS RO/SPS UG/savaitgalių critical spread, RESIDENT HARD ir recovery užraktai lieka pirmesni. Tada šventinis darbas pirmiausia siūlomas norintiems dirbti, po to neutraliems, o norintys ilsėtis naudojami tik kai coverage kitaip neįmanomas. Kiekvienoje grupėje galioja **1 visiems prieš 2 tam pačiam**, o ankstesnių paskelbtų SYSTEM mėnesių švenčių našta naudojama rotacijai.

Jei įprastą darbo dieną sutampa oficiali šventė, scheduleris tą datą traktuoja kaip ne darbo dieną: generuojamas SPS RO budėjimo AM/PM modelis, o įprasti outpatient postai tą dieną yra uždaryti / nepriskiriami; aktyvūs lieka tik SPS RO budėjimo AM/PM slotai. Šventinis pasirinkimas į ORIGINAL request ledger įtraukiamas tik mėnesį, kuriame realiai yra švenčių. SYSTEM holiday burden po publikavimo lieka užšaldytas; swapai ir fairness-neutral repair jo neperrašo.

## SENIŪNĖS NAUDOJIMO IR AUDITO WORKFLOW — V2.5.59

Įrankis nėra „pasitikėk algoritmu“ sistema. Seniūnės darbo modelis yra **Generate → Audit claims → Correct only exceptions → Publish**. Prieš publikavimą seniūnė patikrina HARD diagnostics, kritinį SPS RO / SPS UG / savaitgalių 0–1 spread, blogiausią savaitinį krūvį ir 3–5 rezidentų konkrečius preference / post claim'us. Tikslas – ne dar kartą ranka perskaičiuoti visą grafiką, o patikrinti įrankio teiginius ir išimtis. Pilnas protokolas yra skirtuke **Seniūnės vadovas** ir faile `SENIOR_USABILITY_GUIDE_LT.md`.

## V2.5.61 — savanoriškas dublio perėmimas su aiškiu perspėjimu

Kai realiai prireikia dublio, vien planavimo komforto ribos neturi automatiškai užblokuoti savanorio.

Jei pasirinktam rezidentui dublis sukurtų 12 val. darbo dieną, padidintų 7 dienų krūvį virš maždaug 40 ar 48 val., sukurtų 6 darbo dienų seką, dviejų 12 val. dienų seką arba jis savo noru perimtų pamainą per anksčiau pateiktą RESIDENT HARD laiką, sistema parodo atskirą pasekmių lentelę. Joje turi būti konkretūs skaičiai ir konkreti data / laikotarpis. Tada galima **ATŠAUKTI** arba, gavus aiškų savanorišką sutikimą, **PATVIRTINTI VIS TIEK**.

Tai nėra „ignoruoti visas taisykles“ mygtukas. Manual ACK neapeina ABSOLUTE HARD: pateisinamo neatvykimo / privalomo post-duty poilsio, persidengiančios pamainos, >12 val. per darbo dieną, <11 val. nepertraukiamo paros poilsio, >6 darbo dienų per 7 paeiliui einančias dienas ar aktyviame Rule Profile nustatytos maksimalios 7 dienų swapo / dublio ribos. 48 val. rodoma kaip aiškus perspėjimo slenkstis; galutinį konkretaus darbo laiko režimo teisinį taikymą nustato darbdavys.

Patvirtintas manual override įrašomas dublio audite su parodytomis pasekmėmis ir patvirtinimo laiku. SYSTEM fairness baseline dėl to neperrašomas; tai ACTUAL operacinis savanoriškas sprendimas.


## V2.5.63 — lygaus paskirstymo failsafe
Prieš grąžindama SYSTEM grafiką sistema turi patvirtinti pakankamai lygų darbo vietų paskirstymą. SPS RO, SPS UG ir savaitgaliai įprastai gali skirtis daugiausia 1 paskyrimu tarp daugiausiai ir mažiausiai gavusio rezidento; kitos pagrindinės darbo vietos įprastai — daugiausia 2. Jei per skirtą laiką to patvirtinti nepavyksta, nelygus grafikas negrąžinamas kaip tinkamas. Konkreti SPS data nėra užrakinama vien dėl lygybės: ji gali būti perkelta kitam tinkamam žmogui ar kitai dienai, jei bendras mėnesio paskirstymas išlieka toks pat lygus ir nepažeidžiamos svarbesnės taisyklės.

## V2.5.65 — reta pozicija, atostogos ir automatinė kalendoriaus prenumerata

### Pirmoji ekspozicija retoje pozicijoje

Kai tam tikro posto per mėnesį yra palyginti nedaug, bet vietų pakanka bent po vieną kiekvienam tinkamam rezidentui, sistema pirmiausia siekia, kad **visi gautų bent vieną kartą**, o tik tada skiria išvengiamą antrą kartą tam pačiam žmogui. Tai ypač taikoma Onko RO, Centro UG ir Vaikų UG. SPS RO, SPS UG ir savaitgaliai ir toliau laikomi kuo lygesni tarp rezidentų. Konkreti data nėra „pririšta“ žmogui vien dėl pozicijos balanso — jei tą patį bendrą kiekį galima išlaikyti kita data ir kartu geriau įvykdyti pageidavimą, sistema turi rinktis geresnį išdėstymą.

### Patvirtintos atostogos

`Pageidavimai` lange yra atskiras laukas **Atostogos — patvirtintos nedarbo dienos**. Tai nėra minkštas pageidavimas. Tomis dienomis sistema neskiria nei normalios pamainos, nei dublio, o mėnesio darbo tikslą sumažina proporcingai. Taip atostogos nesukuria dirbtinio „atsilikimo“ nuo kitų rezidentų.

### Pageidavimų pateikimo termino priminimai

`Nustatymuose` pranešimų jungiklis reiškia asmeninius priminimus apie **pageidavimų pateikimo termino datą**. Laukas „Asmeninių priminimų pradžia“ nurodo, nuo kurios ankstesnio mėnesio dienos pradėti siųsti asmeninį countdown, pvz. „Liko 4 dienos iki pageidavimų pateikimo pabaigos“. Pateikus pageidavimus priminimai tam mėnesiui sustoja.

### Mano grafikas kalendoriui

Rezidentas gali:
- atsisiųsti vienkartinį `.ics` failą;
- vieną kartą užsiprenumeruoti privačią iCalendar nuorodą;
- naudoti Google Calendar, Apple Calendar arba Outlook Calendar instrukciją / mygtuką;
- kitai programai naudoti standartinį `.ics` arba iCalendar URL, jei programa jį palaiko.

Prenumerata apima visus paskelbtus ACTUAL mėnesius ir atnaujinama po naujo grafiko publikavimo bei svarbių faktinio grafiko pakeitimų (apsikeitimų, emergency pakeitimų, repairs, dublio faktinio pakeitimo). Jei `Nustatymuose` įjungtas dublių rodymas kalendoriuje, atnaujinamas ir šis pasirinkimas.

Privati kalendoriaus nuoroda turi ilgą atsitiktinį kodą ir turi būti saugoma kaip slaptažodis. Viešame URL nėra rezidento inicialų ar paskyros UUID.


## V2.5.66 — keli vienu metu vykstantys apsikeitimai

Rezidentas gali turėti kelis laukiančius apsikeitimus, jeigu jie liečia skirtingas pamainas. Ta pati konkreti pamaina vienu metu gali būti tik viename aktyviame apsikeitimo pasiūlyme. Jei pamaina jau pasiūlyta kitame swape, sistema parodo aiškią žinutę ir neleidžia sukurti antro konkuruojančio pasiūlymo. Tas pats principas taikomas dublių apsikeitimams. Savo dar nepriimtą pasiūlymą autorius gali atšaukti. Po pritaikyto swapo pamaina vėl gali būti keičiama pagal naują ACTUAL grafiką.


## V2.5.67 — tikslus mėnesio krūvis ir Onko poros

Mėnesio krūvio targetas yra privalomas ir tikslus (nuokrypis 0.0). Onko 08:00–17:00 trunka 9 val., todėl skaičiuojamas kaip 1.5 standartinės 6 val. pamainos. Kad targetas liktų sveikas ir tikslus, Onko SYSTEM grafike skiriamas lyginėmis poromis (0, 2, 4...). To paties mėnesio Onko skirtumas tarp rezidentų negali viršyti 2. Rezidentai, kurie šį mėnesį gauna mažiau Onko, turi prioritetą kitais mėnesiais pagal publikuotą cumulative Onko istoriją.


## V2.5.68 — Onko RO atsigavimo HARD taisyklė

Onko RO yra 9 val. FULL darbo diena. Tas pats rezidentas negali būti paskirtas į Onko RO dvi kalendorines dienas iš eilės. Tai yra ABSOLIUTI generatoriaus taisyklė, ne SOFT pageidavimas ir ne lygybės tikslas.

Taisyklė galioja ir per mėnesio ribą: jei rezidentas paskutinę ankstesnio paskelbto SYSTEM mėnesio kalendorinę dieną dirbo Onko RO, naujo mėnesio 1 d. Onko RO jam negalimas.

Onko porų logika išlieka: individualus Onko skaičius SYSTEM grafike turi būti lyginis, mėnesio skirtumas tarp rezidentų negali viršyti 2, o mažiau Onko gavę rezidentai pasiveja kitais mėnesiais. Tačiau jokio catch-up ar posto lygybės tikslo negalima pasiekti skiriant dvi Onko dienas iš eilės.


## V2.5.69 — savanoriškas Onko swapo override

SYSTEM generavimo metu dvi Onko RO dienos iš eilės lieka draudžiamos: algoritmas jų pats nesudaro. Tačiau po paskelbimo abipusis savanoriškas dviejų rezidentų apsikeitimas gali sukurti dvi Onko RO dienas iš eilės. Tokiu atveju tai rodoma kaip aiškiai patvirtinama pasekmė, o ne kaip automatinis blokas. Tikros ABSOLUTE HARD taisyklės — persidengimas, pateisinama nebuvimo priežastis, minimalus poilsis ir kiti fizinio / teisinio įmanomumo blokai — lieka neapeinami. SYSTEM fairness istorija nuo savanoriško swapo nesikeičia; keičiasi tik ACTUAL grafikas.


## V2.5.70–71 — ilgalaikis pageidaujamos darbo dienos trukmės nustatymas

Nustatymų viršuje kiekvienas rezidentas turi privatų ilgalaikį darbo pobūdžio pasirinkimą **„Pageidaujama darbo dienos trukmė“**. Galimi keturi variantai:

- **Dažniausiai 6 val.** — pageidaujama, kad darbo dienos dažniau būtų trumpesnės.
- **Dažniausiai 12 val.** — pageidaujama, kad darbo dienos dažniau būtų ilgesnės.
- **Mišriai** — siekti 6 val. ir 12 val. darbo dienų mišinio.
- **Nesvarbu** — darbo dienos trukmę parenka optimizatorius pagal likusias taisykles.

**V2.5.71 apsauga:** šis nustatymas negali pats sukurti papildomų dublių. Pirma, be 6/12 val. krypties, nustatomas neutralus visos grupės dublių poreikis; bendras jų skaičius užrakinamas. Tada tas pats dublių kiekis paskirstomas tarp rezidentų, laikant mėnesio dublių skirtumą **max−min ≤2**. Taigi 6 val. pageidavimas nereiškia „be dublių“, o 12 val. pageidavimas nereiškia „pridėti naujų dublių“.

Kai dublis jau reikalingas, konkrečių darbo vietų fazėje pirmiausia stengiamasi, kad tokia diena apimtų bent vieną svarbią **SPS RO arba SPS UG** vietą; sekmadienio budėjimai jau yra SPS RO. Jei dėl aukštesnių taisyklių to padaryti visiems dubliams neįmanoma, paliekamas mažiausias būtinas paprastų postų dublių skaičius.

Onko RO 08:00–17:00 yra atskira svarbi 9 val. pilnos dienos pamaina, tačiau techniškai nėra AM+PM dublis ir į dublių max−min skaičiavimą neįtraukiama.

Nustatymas yra individualus ir kitiems rezidentams ar grupės suvestinėse nerodomas; jį naudoja generatorius sudarydamas konkretų žmogaus grafiką. Privalomos darbo ir poilsio saugos taisyklės, tikslus mėnesio krūvis ir Onko porų taisyklė lieka aukščiau.


## V2.5.73 — ONKO PORŲ ABSOLIUTI TAISYKLĖ

- **Kiekvieno rezidento Onko RO skaičius visada turi būti lyginis: 0, 2, 4, 6...** Tai galioja ir SYSTEM, ir ACTUAL grafikui.
- Viena Onko RO diena yra 9 val. = 1.5 standartinės 6 val. pamainos. Todėl 1, 3, 5... Onko sukurtų 0.5 pamainos trupmeną ir yra ABSOLUTE HARD klaida.
- Mėnesio darbo targetas lieka tikslus: pvz., target 28 reiškia **28.0**, ne 27.5 ar 28.5.
- Jei aktyvių (neužblokuotų) mėnesio Onko dienų skaičius lyginis, užpildomos visos. Jei aktyvių Onko dienų skaičius nelyginis, **viena Onko diena paliekama neužpildyta**, kad bendras užpildytų Onko skaičius būtų lyginis ir jį būtų galima dalyti poromis.
- Savanoriškas apsikeitimas **negali** sukurti 1/3/5 Onko arba 0.5 mėnesio krūvio nuokrypio; toks swapas blokuojamas dar preview etape.
- V2.5.69 consecutive-Onko išimtis lieka siaura: po publikavimo dvi Onko dienos iš eilės gali būti tik ACK pasekmė, jei visi kiti ABSOLUTE HARD išlaikyti. Ji **neleidžia** apeiti Onko parity ar tikslaus targeto.

Trumpai: **EXACT MONTHLY TARGET + ONKO 0/2/4/... = ABSOLUTE HARD VISUR.**


## V2.5.74 — VISŲ POSTŲ STRUKTŪRINIS WATER-FILL

SYSTEM generatorius po darbo datų / AM-PM blokų parinkimo visus ne-Onko postų labelius sprendžia **vienu bendru modeliu**. Kiekvienam postui pirmiausia taikomas floor/ceil entitlement koridorius raw spread 0–1. Tai reiškia, kad trečia ekspozicija negali likti vienam rezidentui, kol kitas tame pačiame poste turi tik vieną, jeigu egzistuoja validus dviejų ar daugiau rezidentų postų perkeitimas, kuris išlaiko darbo datas, blokus, tikslų krūvį ir aukštesnes HARD taisykles.

Jei 0–1 koridorius neturi sprendinio, sistema gali pereiti į 0–2, o po to 0–3 tik tada, kai ankstesnis siauresnis koridorius yra **matematiškai įrodytas neįmanomas**. Timeout nėra toks įrodymas.

Po publikavimo savanoriški bilateraliniai ACTUAL swapai yra fairness-neutral. Jei abu rezidentai sutinka ir nėra tikro saugos / darbo-laiko / fizinio HARD pažeidimo, postų ekspozicijos, UG/Mamografijos kiekiai, diversity ar SYSTEM water-fill nėra swapo blokatoriai. SYSTEM fairness ir postų matrica lieka užšaldyti publikavimo momentu. V2.5.73 tikslus mėnesio workload ir lyginė Onko parity lieka neperžengiami.


## V2.5.77 — PENKTADIENIŲ STRUKTŪRINIS WATER-FILL

SYSTEM generatoriuje penktadieniai yra **struktūrinė HARD fairness taisyklė**. Suskaičiavus visus užpildomus penktadienio priskyrimus, kiekvieno rezidento penktadienių skaičius turi patekti į matematinį `floor(total/rezidentai)..ceil(total/rezidentai)` koridorių. Todėl raw max−min spread turi būti **0–1**.

Pavyzdys: 72 penktadienio priskyrimai / 16 rezidentų = 4.5, todėl teisingas water-fill yra **8 rezidentai po 4 ir 8 rezidentai po 5**, o ne 2–8.

Ši taisyklė taikoma **visiems** SYSTEM penktadienio priskyrimams, įskaitant pageidautas penktadienio datas. Pageidavimas yra SOFT ir negali pralaužti structural 0–1.

Architektūra: Phase 1 subalansuoja darbo datas/blokus ir penktadienius; Phase 2 ant jau subalansuotų blokų kartu water-fill'ina visus ne-Onko postus. Taip penktadienio darbo perkėlimas kartu suteikia postų solveriui galimybę gerinti Mamografijos / ADC / UG / kitų postų matricą.

Po publikavimo abipusis savanoriškas ACTUAL swapas gali išbalansuoti penktadienius ar postus, jei nepažeidžiami tikri saugos / darbo-laiko HARD reikalavimai ir V2.5.73 exact workload + Onko parity. SYSTEM fairness baseline lieka toks, kokį paskyrė algoritmas.


## V2.5.79 — Vizualūs swap requestai ir ONE-WAY EMERGENCY RESCUE

Įprastas `Apsikeitimai` srautas yra **tik bilateralinis swap requestas**: vienas rezidentas pasiūlo savo pamainą už kito rezidento pamainą, gavėjas priima arba atmeta, o po priėmimo seniūnė pritaiko pakeitimą ACTUAL grafike.

Gyvi requestai rodomi kaip platūs vizualūs cards:
- inicialai / vardai nuspalvinti pagal rezidento spalvą;
- rodoma `GAUTA UŽKLAUSA 1/3`, `2/3` ir t. t.;
- aiškiai atskirta, ką siūlytojas ATIDUODA ir kokios gavėjo pamainos PRAŠO;
- gavėjui išsaugojus naują requestą siunčiamas operational email pranešimas, jei jo paskyroje yra email ir SMTP sukonfigūruotas;
- email klaida niekada neatšaukia jau išsaugoto DB requesto.

Po `REQUEST SWAP` nebenaudojamas priverstinis `st.rerun()`, todėl puslapis nebeturi perslinkti į žemiau esantį emergency bloką. Emergency funkcija laikoma atskirame **uždarytame expander**, kuris po normalaus swapo automatiškai neatsidaro.

### ONE-WAY EMERGENCY RESCUE — tai nėra swapas

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

Tai keičia tik ACTUAL operational grafiką. SYSTEM fairness, publication post matrix ir post debt lieka užšaldyti. Nauji rescue įrašai žurnale rodomi `CURRENT LOCATION → MOVING TO` formatu, su spalvotais mover / rescued inicialais. Seni `emergency_actual` bilateraliniai įrašai paliekami tik kaip aiškiai pažymėtas LEGACY auditas.

## V2.5.107 — privalomi „Negaliu dirbti“ ir aiškus pageidavimų auditas

SYSTEM generavime kiekvienas aktyvus **„Negaliu dirbti“** įrašas yra privalomas 0-pažeidimų apribojimas. Jis nėra baudos svoris ir negali būti iškeistas į gražesnį fairness ar didesnį kitų SOFT pageidavimų procentą. Jei safety / coverage / tikslus mėnesio krūvis negali egzistuoti kartu su visais tokiais blokais, SYSTEM juodraštis negrąžinamas.

Po kiekvieno sėkmingo generavimo `Sudarymas` iš karto rodo **Aktyvūs pageidavimai / Įvykdyta / Neįvykdyta / Negaliu dirbti pažeidimai**. Jei visi aktyvūs pageidavimai įvykdyti, rodoma žalia žinutė **„VISI AKTYVŪS PAGEIDAVIMAI ĮVYKDYTI“**. Jei bent vienas SOFT pageidavimas neįvykdytas, šalia rodoma konkreti **NEĮVYKDYTI PAGEIDAVIMAI** lentelė su žmogumi, prašymu ir faktiniu SYSTEM rezultatu. Bet koks `Negaliu dirbti` pažeidimas yra kritinė klaida ir toks SYSTEM juodraštis negali būti publikuojamas.

Kai griežtas struktūrinis 0–1 fairness koridorius nesuderinamas su privalomu 0-HARD sluoksniu, V2.5.107 pirmiau saugo visus HARD blokus. Fallback tada bounded-feasibility būdu bando išlaikyti visus konkrečių datų SOFT prašymus ir work-style tikslus; tik žemesnio rango sluoksniai gali būti atlaisvinami. Kas liko neįvykdyta, niekada neslepiama — tai matoma audito lentelėje.


## V2.5.108 — LIVE pageidavimų palyginimas

ŠR tyrimo lange `AVAILABLE GPT + HUMAN vs MY ENGINE` galima pasirinkti **LIVE APP WISHES / HARD**. Šis režimas paima pasirinkto mėnesio realius pageidavimus tiesiai iš programos duomenų bazės, prieš užrakinimą parodo jų suvestinę ir sukuria nekintamą snapshot. **Tas pats snapshot naudojamas abiem grafikams**: rankiniam / GPT+human ir MY ENGINE. Galutinis rankinis grafikas niekada nenaudojamas pageidavimams atkurti. Po Run 1 rodoma tiesioginė kiekvieno pageidavimo išpildymo lentelė.

## V2.5.109 — Excel atsisiuntimas Sudaryme ir Grafiko tvirtinime

- **Sudarymas** lange po sugeneruotu SYSTEM juodraščiu visada rodomi du aiškūs mygtukai: **ATSISIŲSTI EXCEL (.xlsx)** ir **ATSISIŲSTI CSV (.csv)**.
- **Grafikas → Grafiko tvirtinimas** lange tas pats kandidatas gali būti atsisiųstas Excel ir CSV formatu dar **prieš FINAL patvirtinimą**.
- Dabartiniam **ACTUAL** grafikui taip pat visada rodomi abu formatai.
- Užrakinus **FINAL**, administracijai skirta spalvota Excel versija lieka pagrindinis failas, o šalia pateikiamas ir FINAL CSV.
- Excel faile išlaikomas grafiko tinklelis, rezidentų spalvos, Suvestinė ir Dublių lapas. Streamlit lentelės viršutiniame dešiniajame kampe esantis „Download as CSV“ nėra vienintelis eksportas.

