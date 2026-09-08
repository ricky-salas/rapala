# V2.5.149 — PASSWORD RECOVERY

## Kas pridėta

- Prisijungimo lange pridėtas **„Pamiršau slaptažodį?“** blokas.
- Vartotojas įveda savo paskyros el. paštą ir gauna Supabase recovery laišką.
- Atsakymas sąmoningai neatskleidžia, ar toks el. paštas registruotas.
- Iš recovery laiško grįžus į RAPA atsidaro **naujo slaptažodžio forma**.
- Slaptažodis turi būti bent 8 simbolių ir įvestas vienodai du kartus.
- Po sėkmingo pakeitimo recovery tokenas pašalinamas iš URL ir vartotojas priverstinai grąžinamas į švarų prisijungimą.

## Saugumas

- `access_token` skaitomas tik naršyklėje iš URL fragmento (`#...`).
- Tokenas **neperkeliamas į Streamlit query parametrus**, Python session state, DB ar logus.
- Slaptažodis atnaujinamas tiesiogiai per Supabase Auth `PUT /auth/v1/user` su recovery access tokenu.
- `resident_invites`, `user_profiles`, inicialai ir istorinis `user_id` nėra keičiami.

## Konfigūracija

Production'e turi būti nustatytas:

`SCHEDULER_PUBLIC_URL = "https://rapala-6klwqxgg4ggahret5mddla.streamlit.app/"`

Tas pats URL turi būti leidžiamas Supabase Auth kaip **Site URL** arba **Redirect URL**. Jei `SCHEDULER_PUBLIC_URL` nėra nustatytas, Supabase naudos projekto Site URL.

## Deivydas

Deivydo paskyros nereikia kurti iš naujo. Po šio buildo deploy jis login lange renkasi **„Pamiršau slaptažodį?“**, įveda `giedrimd@gmail.com`, atsidaro gautą laišką ir nusistato naują slaptažodį. Jo `GD` profilis ir visi prie `user_id` pririšti duomenys lieka tie patys.
