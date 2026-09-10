# V2.5.165 — DUTY WATER-FILL + NIGHT-ONLY REST

Pataisyta kritinė SPS RO budėjimų logika.

1. Visi SPS RO budėjimai (savaitgalio / šventiniai FULL + NIGHT) dabar turi atskirą ABSOLUTE water-fill skaitiklį. Mėnesio kiekis kiekvienam rezidentui privalo būti tik floor arba ceil nuo bendro budėjimų skaičiaus. Ši taisyklė neatsipalaiduoja structural fallback režime.
2. Bet kokio budėjimo dieną išlieka VERY HARD draudimas skirti kitą RAPA pamainą.
3. Privaloma visa sekanti laisva diena taikoma TIK po NIGHT budėjimo. Dieninis / savaitgalio FULL budėjimas automatiškai kitos dienos neblokuoja.
4. Cross-month poilsio carry-over dabar fiksuoja tik ankstesnio mėnesio paskutinės dienos NIGHT budėjimą.
5. 2026-10-30 SPS RO NIGHT = GE; 2026-10-31 GE OFF lieka HARD.
6. Validatorius ir Taisyklės atnaujinti pagal tą pačią semantiką.
