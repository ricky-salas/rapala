# RAPA V2.5.160 — AUTH RECOVERY + PERSISTENT SESSION

- „Pamiršau slaptažodį“ workflow sutvarkytas nuo pradžios iki galo.
- Atkūrimo laiškas grąžina į dabartinį RAPA adresą (SCHEDULER_PUBLIC_URL, o jei jo nėra — aktyvus Streamlit URL / forwarded host).
- Atidarius recovery nuorodą RAPA pateikia naujo slaptažodžio formą.
- Po sėkmingo slaptažodžio pakeitimo sistema sukuria šviežią normalų Supabase prisijungimą ir vartotoją prijungia automatiškai.
- Access/refresh tokenai neperkeliami į Streamlit query parametrus.
- Prisijungimo sesija išsaugoma Secure + SameSite=Lax RAPA naršyklės slapukuose 30 dienų ir atkuriama po browser reload / naujos Streamlit WebSocket sesijos.
- Atsijungimas panaikina Supabase sesiją ir išvalo RAPA auth slapukus.
- V2.5.159 planavimo / Onko cycle / Suvestinė logika nepakeista. scheduler_engine.py pakeistas tik ENGINE_API_VERSION į 2.5.160, kad app/engine deploy pora būtų aiškiai sinchronizuota.
