# V2.5.157 — ADMIN STATIONS + NO BLOCK

Patvirtinti 2026-09-10 SP / administracijos pakeitimai įdėti ant V2.5.156 bazės.

- MUST: CENTRO RO 4 AM + 4 PM, SPS RO AM + PM, Centro UG 120 AM, Onkologinė/TBL, Skopijos, budėjimai.
- II prioritetas: Vaikų UG AM, ADC 144/145 AM, Centro UG 120 PM.
- III / paskutinis prioritetas: ADC 144/145 PM, SPS UG AM.
- SPS UG PM nuo spalio pašalintas iš aktyvaus grafiko (vidinis blocked tombstone paliktas tik ID suderinamumui).
- Skopijos nuo 2026-10: viena AM eilutė pirmadieniais–ketvirtadieniais, 08:00–14:00.
- Įprasta vieta: Centras, 0153 kab., skrandžio skopijos.
- 2026-10-13: konsultacinė poliklinika, 209 kab., žarnų skopijos.
- Mammografija nuo spalio lieka neaktyvi ir nematoma.
- Visuose žmogui rodomuose grafikuose blocked / inactive slotai neberodomi kaip `BLOCK`; jie tiesiog neegzistuoja matomame grafike.
- Budėjimų HARD logika palikta tokia, kokia buvo V2.5.156; ji neperkelta į „preferably“.
- SPS RO naktinis budėjimas neaktyvuotas, nes dar nėra patvirtintų pilnų valandų / dažnio parametrų.

Engine API: 2.5.157.
