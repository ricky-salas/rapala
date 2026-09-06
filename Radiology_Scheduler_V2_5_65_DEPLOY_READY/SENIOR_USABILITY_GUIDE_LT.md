# SHIFT HAPPENS — SENIŪNĖS DARBO IR SISTEMOS VADOVAS

**Versija:** V2.5.128  
**Paskirtis:** kasdieniam darbui, naujų naudotojų mokymui ir sistemos pristatymui komandai.

> **Pagrindinė mintis:** sistema kiekvieną mėnesį siekia 100 % pageidavimų išpildymo. Sudėtingame mėnesyje realus rezultatas gali būti mažesnis, pavyzdžiui, 93 %, jeigu dalies pageidavimų vienu metu įvykdyti neleidžia saugos, padengimo, darbo krūvio ar tarpusavio konfliktai. Sistema vis tiek ieško geriausio įmanomo sprendinio.

## 1. Kaip sistemą paaiškinti vienu sakiniu

Sistema pirmiausia sudaro **saugų, pilnai padengtą ir kuo tolygiau paskirstytą grafiką**, tada siekia maksimaliai įvykdyti visų rezidentų pageidavimus, o pateikimo eilę naudoja tik tada, kai lieka keli vienodai geri, bet tarpusavyje nesuderinami variantai.

## 2. Penki sprendimo lygiai

| Lygis | Kas saugoma | Praktinė reikšmė |
|---|---|---|
| 1 | Saugumas, įmanomumas ir privalomas padengimas | Negali būti persidengimų, fiziškai neįmanomų paskyrimų ar nepadengtų privalomų vietų. |
| 2 | „Dirbti negaliu“ | Tikslas — 0 pažeidimų. |
| 3 | Tolygus privalomo krūvio ir darbo vietų paskirstymas | Savaitgaliai, SPS RO, SPS UG, penktadieniai ir kitos vietos paskirstomos kuo lygiau. |
| 4 | Visų rezidentų pageidavimai | Sistema siekia didžiausio įmanomo išpildymo; tikslas visada 100 %. |
| 5 | Pateikimo vieta 1–16 | Naudojama tik likusiam konfliktui tarp vienodai gerų sprendinių. |

**Svarbu:** pateikimo vieta nevaldo viso grafiko ir nemažina bendro pageidavimų rezultato vien tam, kad ankstesnis pateikėjas laimėtų. Pirmiausia randamas geriausias įmanomas bendras rezultatas.

## 3. Pageidavimų logika be techninio žargono

Rezidentui pakanka keturių paprastų sąvokų:

- **Dirbti negaliu** — visa diena, rytas arba popietė, kai žmogus iš tikrųjų negali dirbti.
- **Noriu laisvos** — noras turėti laisvą konkrečią dieną ar jos dalį.
- **Pageidauju dirbti** — noras dirbti konkrečią dieną ar jos dalį.
- **Pateikimo vieta** — 1–16 vieta tam pačiam grafikui; tai tik paskutinis konflikto sprendimo kriterijus.

Sistema visada pradeda nuo tikslo įvykdyti **visus** pageidavimus. Jeigu tai įmanoma, pateikimo vieta nieko nekeičia.

### Pavyzdys

Tarkime, sudėtingą mėnesį geriausias įmanomas rezultatas yra **93 %**, nes keli pageidavimai tarpusavyje kertasi arba juos riboja svarbesnės saugos, padengimo ir darbo krūvio taisyklės. Sistema pirmiausia išsaugo tą geriausią bendrą rezultatą. Tik likusioje konfliktų dalyje, kai yra keli vienodai geri variantai, gali būti naudojama pateikimo vieta.

## 4. Mėnesio ciklas: 1–14–15–16

| Laikas | Etapas | Kas vyksta |
|---|---|---|
| 1 d. 00:00 – 14 d. 00:00 | Pageidavimų teikimas | Rezidentai pildo ir koreguoja pageidavimus. |
| 14 d. 00:00 – 15 d. 00:00 | Seniūnės parengimo langas | Generuojamas, tikrinamas ir prireikus koreguojamas preliminarus grafikas. |
| Iki 15 d. 00:00 | Preliminarus paskelbimas | Preliminarus grafikas paskelbiamas rezidentams. |
| 15 d. 00:00 – 16 d. 00:00 | 24 val. apsikeitimų langas | Rezidentai gali siūlyti apsikeitimus; jie įsigalioja tik po reikalingų sutikimų ir seniūnės patvirtinimo. |
| Nuo 16 d. 00:00 | Galutinė patikra | Rezidentų savitarna užrakinama; seniūnė sutikrina išimtis, prireikus atlieka rankines korekcijas ir paskelbia galutinį grafiką. |

Visi laikai — Lietuvos laiku.

## 5. Seniūnės darbo eiga

### Iki 14 d. 00:00
1. Patikrinti, ar visi pateikė pageidavimus.
2. Peržiūrėti tik neaiškius ar akivaizdžiai prieštaringus įrašus.
3. Nereikia iš anksto ranka konstruoti viso grafiko.

### 14–15 d.
1. Paleisti generatorių.
2. Patikrinti, ar privalomų klaidų skaičius yra 0.
3. Patikrinti „Dirbti negaliu“ pažeidimus — turi būti 0.
4. Peržiūrėti darbo vietų ir privalomo krūvio pasiskirstymą.
5. Peržiūrėti pageidavimų išpildymą ir neįvykdytų pageidavimų priežastis.
6. Jei yra reali problema, pakartoti generavimą arba atlikti pagrįstą rankinę korekciją.
7. Iki 15 d. 00:00 paskelbti preliminarų grafiką.

### 15–16 d.
1. Stebėti apsikeitimų prašymus.
2. Apsikeitimas įsigalioja tik po abiejų rezidentų sutikimo ir seniūnės patvirtinimo.
3. Saugos patikros išlieka aktyvios.

### Nuo 16 d. 00:00
1. Rezidentų savitarna užrakinta.
2. Patikrinti laukiančius sprendimus ir išimtis.
3. Prireikus atlikti rankinę korekciją.
4. Paspausti **„Paskelbti galutinį grafiką“**.

## 6. Saugos ir darbo laiko apsaugos

| Apsauga | Generavimo principas |
|---|---|
| Darbo trukmė per dieną | Iki 12 val. |
| Poilsis tarp atskirų darbo dienų | Bent 11 val. |
| Darbo dienos per slenkantį 7 d. langą | Iki 6 |
| Žinomos darbo valandos per slenkantį 7 d. langą | Iki 48 val. generuojant |
| Po ilgo / naktinio budėjimo | Konservatyvi poilsio apsauga |
| Persidengiančios pamainos | Neleidžiamos |
| Privalomas padengimas | Negali būti aukojamas dėl gražesnio pageidavimų procento |

Po paskelbimo savanoriškam apsikeitimui gali būti rodoma pasekmių ir papildomo patvirtinimo lentelė. Kritinės poilsio, persidengimo ir privalomo padengimo apsaugos išlieka.

## 7. Darbo vietų ir privalomo krūvio paskirstymas

Pagrindinės kategorijos: **CENTRO RO, Onko RO, SPS RO, Centro UG, SPS UG, ADC 144, ADC 145, Vaikų UG, Mamografijos**.

### Kritinės ekspozicijos

- SPS RO;
- SPS UG;
- savaitgalių darbas.

Kai matematiškai įmanoma, sistema siekia, kad šių ekspozicijų skirtumas tarp rezidentų būtų **0–1**. Platesnis skirtumas leidžiamas tik tada, kai siauresnis paskirstymas neįmanomas dėl svarbesnių apribojimų.

### Kitos darbo vietos

Sistema pirmiausia stengiasi suteikti visiems panašią ekspoziciją konkrečiai darbo vietai prieš skirdama perteklinius pakartojimus tam pačiam žmogui, kai tai suderinama su aukštesnėmis taisyklėmis ir pageidavimais.

### Onko RO

- kiekvieno rezidento Onko paskyrimų skaičius turi būti lyginis: 0, 2, 4 ir t. t.;
- tas pats rezidentas negali dirbti Onko dvi kalendorines dienas iš eilės;
- vertinama ir mėnesio riba, jei ankstesnio mėnesio paskutinę dieną žmogus dirbo Onko.

### Nėra automatinės „skolos“ kitam mėnesiui

Po savanoriškų apsikeitimų ar rankinių pakeitimų sistema nepriverčia kitą mėnesį „atsigriebti“. Ankstesni mėnesiai lieka istorijai ir auditui, o naujas mėnuo pradedamas nuo naujo bazinio paskirstymo.

## 8. Dubliai

- Dublis yra atskiras parengties sluoksnis, o ne automatiškai papildoma darbo pamaina.
- Savaitgalio dublių vietos rezervuojamos pagal nustatytą mėnesio ciklą.
- Jei dalis rezidentų nepasirenka dublio patys iki užrakinimo, likusios privalomos vietos paskirstomos automatiškai tarp tinkamų rezidentų.
- Dublio paskyrimas savaime nekeičia normalaus darbo grafiko.
- Tik realiai įvykęs pavadavimas tampa faktiniu darbu ir registruojamas audite.

## 9. Apsikeitimai ir rankinės korekcijos

### Savanoriškas apsikeitimas
1. Vienas rezidentas pasiūlo apsikeitimą.
2. Kitas rezidentas sutinka.
3. Sistema patikrina saugos ir darbo laiko pasekmes.
4. Seniūnė patvirtina arba atmeta.
5. Tik po patvirtinimo pakeitimas tampa faktinio grafiko dalimi.

### Liga / nenumatytas įvykis / kritinis padengimas

Tokie pakeitimai registruojami kaip faktinio darbo realybė. Jie nekeičia to, kaip buvo vertinamas pradinis algoritmo sudarytas grafikas, ir nesukuria automatinės skolos kitam mėnesiui.

## 10. Pradinis ir faktinis grafikas

| Sąvoka | Reikšmė |
|---|---|
| Pradinis grafikas | Paskelbtas bazinis variantas, pagal kurį vertinamas algoritmo rezultatas. |
| Faktinis grafikas | Dabartinė reali versija po apsikeitimų, ligų, pavadavimų ir rankinių korekcijų. |

Rezidentui kasdien svarbiausias faktinis grafikas. Tyrimui ir sistemos kokybės auditui išsaugomas ir pradinis variantas.

## 11. Penkių minučių patikra prieš paskelbimą

1. Privalomų klaidų skaičius = 0.
2. „Dirbti negaliu“ pažeidimų = 0.
3. Nėra trūkstamų privalomų SPS / savaitgalio vietų.
4. Kritinis krūvis ir savaitgaliai nėra akivaizdžiai sukrauti vienam žmogui.
5. Darbo vietų pasiskirstymas atitinka sistemos nurodytą geriausią įmanomą lygumą.
6. Neįvykdyti pageidavimai turi suprantamą ir patikrinamą priežastį.
7. Prieš galutinį paskelbimą nėra likusių neaiškių apsikeitimų ar korekcijų.

### Kada nepaskelbti

- yra privaloma saugos klaida;
- yra „Dirbti negaliu“ pažeidimas;
- trūksta privalomo padengimo;
- sistemos suvestinė nesutampa su pačiu grafiku;
- importuoti pageidavimai akivaizdžiai nepilni;
- liko konfliktas, kurio priežasties negalima paaiškinti.

## 12. Paprastas ir Išplėstinis režimai

| Režimas | Kam skirtas | Kas rodoma |
|---|---|---|
| Paprastas | Kasdieniam rezidento naudojimui | Pageidavimai, grafikas, apsikeitimai, dubliai, kalendorius, tyrimo anketa. |
| Išplėstinis | Seniūnės / tyrėjo / techninei patikrai | Detalesnė diagnostika, teisingumo rodikliai, audito informacija ir tyrimo funkcijos. |

## 13. Tyrimo langas

Grafikų sudarymo metodų palyginimas yra perkeltas į **Tyrimo** langą ir nėra atskiras pagrindinės navigacijos langas. Jis skirtas tyrimo darbui ir neturi keisti realaus grafiko sudarymo taisyklių.

## 14. 60 sekundžių pristatymo tekstas

> „Mūsų sistema kiekvieną mėnesį siekia 100 procentų pageidavimų išpildymo. Pirmiausia ji saugo saugumą, privalomą padengimą ir tikrą negalėjimą dirbti. Tada kuo tolygiau paskirsto privalomą krūvį ir darbo vietas, o po to ieško geriausio įmanomo visų pageidavimų rezultato. Sudėtingame mėnesyje rezultatas gali būti mažesnis, pavyzdžiui, 93 procentai, jeigu dalies norų vienu metu įvykdyti neįmanoma. Pateikimo vieta įsijungia tik pačiame gale — kai lieka keli vienodai geri, bet tarpusavyje konfliktuojantys variantai. Po preliminaraus paskelbimo turime 24 valandų apsikeitimų langą, o tada seniūnė atlieka galutinę patikrą ir paskelbia galutinį grafiką.“

## 15. Atmintinė viename ekrane

| Kada | Ką daryti |
|---|---|
| 1–14 d. | Rezidentai pildo pageidavimus. |
| 14–15 d. | Generuoti, tikrinti, taisyti; iki 15 d. 00:00 paskelbti preliminarų grafiką. |
| 15–16 d. | 24 val. apsikeitimų langas. |
| Nuo 16 d. | Rezidentų savitarna užrakinta; galutinė rankinė patikra; paskelbiamas galutinis grafikas. |
| Visada | Tikslas 100 % pageidavimų, 0 „Dirbti negaliu“ pažeidimų, saugus ir kuo lygesnis privalomas krūvis. |
| Pateikimo vieta | Tik paskutinis vienodai gero neišsprendžiamo konflikto kriterijus. |
