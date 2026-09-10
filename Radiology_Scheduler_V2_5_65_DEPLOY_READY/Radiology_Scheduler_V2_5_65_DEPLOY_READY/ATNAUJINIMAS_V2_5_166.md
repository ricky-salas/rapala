# V2.5.166 — Generation UX

- **SP ir ŠR pirmas matomas tabas dabar yra SUDARYMAS**, ne Pageidavimai. Todėl po `st.rerun()` operatorius nebeišmetamas iš grafiko kūrimo darbo eigos. Rezidentams navigacija nesikeičia.
- Po sėkmingo GENERUOTI ir GERINTI nebėra papildomo priverstinio rerun — naujas draftas užkraunamas tame pačiame Sudarymo lange.
- Pagrindinis iteracijos veiksmas aiškus: **BANDYTI GERESNĮ GRAFIKĄ — SAUGOTI TIK JEI GERESNIS**. Esamas validus draftas neprarandamas, jei kandidatas blogesnis.
- Nepaskelbtą draftą galima išmesti vienu mygtuku **IŠMESTI TIK JUODRAŠTĮ**; pageidavimai, HARD, recurring ir credit pasirinkimai lieka.
- Paskelbto grafiko pilnam resetui nebereikia ranka rašyti `RESET YYYY-MM`: pakanka aiškaus patvirtinimo checkbox + vieno mygtuko. Serverio saugikliai FINAL / completed backup istorijai lieka. Po reset automatiškai grįžtama į SUDARYMĄ.
- Scheduling engine API nesikeičia: lieka **2.5.165**. Tai UI/workflow release, todėl V2.5.165 duty water-fill ir NIGHT-rest logika lieka byte-identical.
