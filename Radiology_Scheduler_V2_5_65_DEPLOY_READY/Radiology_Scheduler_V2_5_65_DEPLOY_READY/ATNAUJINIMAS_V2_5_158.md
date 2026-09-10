# V2.5.158 — SP / admin update 2026-09-10

## Kas pakeista

- **Onko/TBL** nuo 2026-10 yra viena **08:00–17:00 FULL** pamaina, o ne atskiros AM/PM eilutės.
- Viena Onko/TBL diena = **1,5 įprastos 6 h pamainos vieneto** (`workload2=3`). Lyginių porų HARD taisyklė išsaugota: Onko skiriamas 0/2/4… dienomis; esant 22 spalio darbo dienoms 11 rezidentų gauna po 2 Onko dienas.
- **2026 m. spalį Onko/TBL leidžiama tik tiems rezidentams, kurie rugsėjį Onko nedirbo.** Ši būsena skaitoma iš ankstesnio mėnesio efektyvaus ACTUAL grafiko ir perduodama į frozen request snapshot, todėl taisyklė išlieka validuojant juodraštį.
- **SPS UG 1035 PM grąžinta** kaip reali aktyvi vakaro eilutė. Kadangi naujausioje SP žinutėje jos prioritetas nenurodytas, ji nepakelta į MUST savavališkai — kol kas laikoma III / optional kartu su SPS UG AM.
- Esamas **SPS RO budėjimų HARD modelis nekeistas**.
- Grafike **Centro UG 120 AM ir PM rodomos greta**.
- Pridėta matoma **„SPS RO naktiniai budėjimai“** eilutė kaip vizualus scaffold. Naktinių datų / valandų / workload engine negeneruoja, nes jų SP žinutėje nebuvo pateikta; taip išvengiama sugalvotų operacinių duomenų.
- Rezidentų inicialų tekstas schedule lentelėje suvienodintas į **baltą** tiek Streamlit lentelėje, tiek Excel grafiko lape.
- `BLOCK` vartotojo grafike ir toliau nerodomas.

## Svarbus sąmoningas ne-pakeitimas

Naktinių SPS RO budėjimų operacinė logika neaktyvuota. Kai bus patvirtintos konkrečios datos / valandos / darbo krūvio vertė, scaffold eilutę galima prijungti prie tikrų `NIGHT` slotų atskiru mažu leidimu.
