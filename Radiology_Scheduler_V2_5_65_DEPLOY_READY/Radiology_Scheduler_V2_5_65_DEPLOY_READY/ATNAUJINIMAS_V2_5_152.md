# RAPA Scheduler V2.5.152 — STRICT FAIRNESS + WISH AUDIT

## Kas pataisyta

### 1. HARD konfliktuojantis SOFT pageidavimas nebeskaičiuojamas kaip nesėkmė
Jei tam pačiam laikui yra `Negaliu dirbti` ir `Pageidauju dirbti`, HARD taisyklė laimi dar prieš solverį. Pradinis pageidavimas išsaugomas auditui, bet pažymimas `INACTIVE` ir neįtraukiamas į aktyvių pageidavimų vardiklį.

### 2. Savaitgalio `Pageidauju dirbti` dabar realiai optimizuojamas
Savaitgalio pageidavimai nebėra tik post-hoc statistika. SOFT1 ir SOFT2 optimizavimas apima darbo dienas ir savaitgalius. Pirmiausia maksimalizuojamas įvykdytų pageidavimų skaičius, tada, kai bendras maksimumas vienodas, konfliktą sprendžia pateikimo prioritetas.

### 3. Fairness nebeatlaisvinamas dėl timeout
Griežtas struktūrinis koridorius pirmiausia kartojamas su ilgesniu laiku. Platesnis weekend / Friday fairness koridorius leidžiamas tik tada, kai ankstesnis koridorius solverio yra **matematiškai įrodytas neįmanomas** (`infeasible`), o ne tada, kai tiesiog nebuvo gautas kandidatas laiku.

### 4. Penktadieniai vertinami pagal realią HARD talpą
Penktadienio fairness vartai naudoja kiekvieno rezidento HARD-eligible entitlement, o ne naivų visų rezidentų raw max–min. Raw skirtumas lieka audite, tačiau fairness klaida yra nukrypimas nuo matematiškai pasiekiamo entitlement koridoriaus.

### 5. Generatorius ir validatorius turi tą pačią savaitgalio semantiką
SYSTEM bazinis fairness skaičiuojamas pagal raw Saturday / Sunday / weekend krūvį. Pageidavimas dirbti savaitgalį nesuteikia teisės automatiškai turėti didesnį savaitgalio burden; jis optimizuojamas tik jau leistino fairness koridoriaus viduje.

### 6. Tikros neįvykdymo priežastys
`Pageidauju dirbti` nebeaiškinamas kaip „nėra tinkamos pamainos“, jei pamaina egzistuoja, bet ją gavo kitas žmogus. Tokiu atveju rodoma, kad tai buvo pageidavimų paskirstymo konfliktas, kartu išsaugant konkuruojančią pamainą ir jos gavėją.

## Dabartinio spalio scenarijaus regresijos testas
V2.5.152 testas su dabartiniam 2026-10 įvedimui artimu 16 rezidentų scenarijumi patvirtina:
- `0 HARD` klaidų;
- `0 Resident-HARD` praradimų;
- Friday entitlement gate = PASS;
- Friday relaxation radius = `0`;
- HARD konfliktuojantis PV 2026-10-20 `Pageidauju dirbti` lieka audite, bet nėra score denominator;
- vienintelio 2026-10-04 savaitgalio darbo konflikto atveju max-count užrakinamas pirmiau, o tada pateikimo prioritetas teisingai išsprendžia MR / VL tie-break;
- revalidation išsaugo tą pačią semantiką.

## Diegimas
- `app.py` ir `scheduler_engine.py` reikia diegti **kartu**.
- Supabase migracijos šiai laidai nereikia.
- V2.5.150 legacy-draft guard ir V2.5.151 HARD-aware Friday capacity logika išlieka aktyvūs.
