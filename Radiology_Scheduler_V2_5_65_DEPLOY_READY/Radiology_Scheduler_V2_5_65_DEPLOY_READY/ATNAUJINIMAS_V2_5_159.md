# V2.5.159 — Onko ciklo apskaita

- Įvestas tęstinis Onko/TBL 2 dienų porų ciklas.
- Oficialus 2026 m. rugsėjo seed pagal SP: SE, KE, MR, ŠR, GB, GD, DU, SA, MŽ, GE, PV — po 2 Onko dienas.
- Spalį pirmiausia Onko porą gauna likę rezidentai su mažiausiu kaupiamuoju skaičiumi; užpildžius juos ciklas tęsiamas iš naujo.
- Panaikintas per griežtas V2.5.158 principas, kuris visus rugsėjį dirbusius Onko visiškai blokavo spalį.
- Suvestinėje rodomi: „Onko iki mėnesio“, „Onko šį mėnesį“, „Onko ciklas iš viso“.
- Bendra kitų darbo vietų istorijos skola lieka išjungta; šis longitudinalinis ciklas taikomas tik Onko.
- Supabase migracijos nereikia: ciklo istorija remiasi oficialiu rugsėjo seed + paskelbtais SYSTEM grafikais.
