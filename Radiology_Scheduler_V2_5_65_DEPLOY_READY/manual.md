# Manual

V2.5.6 BETA LOCKED naudoja atskirus `manual_lt.md` ir `manual_en.md` dokumentus. Fairness hierarchija, Monthly/Cumulative formulės ir interpretacija aprašytos abiejose versijose. Portale manualą gali redaguoti tik seniūnės profilis.


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



## V2.5.58 — Public-holiday allocation

Settings now include one persistent normalized SOFT signal: **prefer holiday work**, **neutral**, or **prefer holiday rest**. This is not a right to claim or avoid every holiday.

Official Lithuanian public holidays use a dedicated preference-cohort water-fill layer after ABSOLUTE HARD, critical SPS/weekend equality, Resident-HARD and weekly-recovery locks. Holiday duty goes to holiday-work volunteers first, neutral residents next, and holiday-rest residents only when coverage requires it. Within each cohort, one holiday unit is distributed across peers before a second unit is given to the same person, and prior published SYSTEM holiday burden is used for longitudinal rotation.

A statutory holiday falling on a weekday uses the non-working-day SPS RO AM/PM duty pattern rather than ordinary outpatient rows. The holiday preference enters the frozen ORIGINAL request ledger only in months that actually contain public holidays. Post-publication swaps/repairs do not rewrite SYSTEM holiday burden.

## V2.5.65 update

- Sparse educational posts: everyone receives a first exposure before avoidable second exposures when mathematically feasible.
- Approved vacation/leave: separate absolute no-work input with proportional workload-target reduction.
- Reminder setting: explicitly tied to the preference-submission deadline and its concrete date.
- Personal calendar: one-time `.ics` plus private multi-month subscription URL; automatic best-effort refresh after publication and important ACTUAL changes; Google / Apple / Outlook handoff and generic iCalendar fallback.


## V2.5.67 — tikslus mėnesio krūvis ir Onko poros

Mėnesio krūvio targetas yra privalomas ir tikslus (nuokrypis 0.0). Onko 08:00–17:00 trunka 9 val., todėl skaičiuojamas kaip 1.5 standartinės 6 val. pamainos. Kad targetas liktų sveikas ir tikslus, Onko SYSTEM grafike skiriamas lyginėmis poromis (0, 2, 4...). To paties mėnesio Onko skirtumas tarp rezidentų negali viršyti 2. Rezidentai, kurie šį mėnesį gauna mažiau Onko, turi prioritetą kitais mėnesiais pagal publikuotą cumulative Onko istoriją.
