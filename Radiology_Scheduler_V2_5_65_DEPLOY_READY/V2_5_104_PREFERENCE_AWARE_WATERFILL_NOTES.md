# V2.5.104 — PAGEIDAVIMAMS JAUTRUS WATER-FILL + ONKO-0 → MAMOGRAFIJA

> **Šis skyrius patikslina V2.5.96/V2.5.103 SYSTEM water-fill konstituciją. Jis yra viršesnis ten, kur ankstesni tekstai teigė, kad savaitgalio pageidavimas niekada negali padidinti SYSTEM RAW savaitgalių spread.**

- **Aiškus „Pageidauju dirbti“ savaitgalį yra savanoriškas nepopuliaraus krūvio pasirinkimas.** Jei rezidentas konkrečiai pageidauja šeštadienio / sekmadienio datos (įskaitant ilgalaikį recurring pageidavimą), generatorius stengiasi šį prašymą įvykdyti prieš versdamas neutralų ar nenorintį rezidentą dirbti tą patį nepopuliarų krūvį, jei leidžia ABSOLUTE HARD, poilsis, coverage ir tikslus mėnesio krūvis.
- **Water-fill niekur nedingsta.** Fairness 0–1 taikomas LIKUSIAM NESAVANORIŠKAM šeštadienių, sekmadienių ir savaitgalio SPS RO krūviui. Dėl savanoriškų pageidavimų RAW savaitgalių / SPS RO spread gali būti >1 jau SYSTEM grafike. RAW ekspozicija vis tiek rodoma atskirai.
- **SPS UG lieka struktūrinė kritinė kategorija.** Savanoriško savaitgalio išimtis nekeičia SPS UG raw water-fill.
- **Vienas rezidentas per konkretų šeštadienio+sekmadienio savaitgalį vis tiek gali turėti daugiausia vieną savaitgalio budėjimą.** Savanoriškumas keičia fairness apskaitą, ne fizinio savaitgalio unikalumo taisyklę.
- **Po publikavimo bilateral swapai ir kiti leidžiami ACTUAL pakeitimai gali RAW balansą pakeisti dar labiau.** SYSTEM lieka auditui; jokio kito mėnesio catch-up nėra.
- **Mamografija lieka paskutinio prioriteto neprivalomas kabinetas.** Kai jau nustatyta, kiek Mamografijos slotų apskritai lieka užpildyti po optional-gap pasirinkimo, rezidentams, kurie tą mėnesį turi **0 Onko RO**, pirmiausia stengiamasi duoti bent po vieną likusią Mamografijos ekspoziciją. Tai yra current-month post-breadth prioritetas struktūrinio postų koridoriaus viduje; jis negali pabloginti jau įrodyto postų spread guardrailo.
- V2.5.104 naujos duomenų bazės migracijos nereikia.

