# V2.5.148 — Anketa + Swap + pamainos atidavimo registras

- `Swap` pakeičia pagrindinės navigacijos pavadinimą `Apsikeitimai`.
- Abipusio swap logika nekeista: abi pusės sutinka, SP pritaiko po galutinės patikros.
- Pridėtas vienpusio pamainos atidavimo registras tame pačiame `Swap` lange.
- `Noriu atiduoti` registruoja atvirą atidavimo įrašą.
- `Atidaviau pamainą` registruoja donorą, gavėją, pamainą ir registracijos laiką.
- SP ir ŠR mato visą registrą; kiti rezidentai tik savo donor/gavėjo įrašus.
- Atidavimo registras pats nekeičia ACTUAL — tai sąmoninga audito apsauga.
- Anketa išlieka prieinama visiems rezidentams Paprastame ir Išplėstiniame režime; tyrėjo diagnostika lieka tik SP/ŠR Išplėstiniame režime.
- Įtrauktas V2.5.147 Nustatymų cleanup: paslėpti seni email/SMS/reminder kontroliai, backend reikšmės išlaikomos.
- V2.5.146 Specialios dienos / post-publication Dubliai logika išlaikyta.
