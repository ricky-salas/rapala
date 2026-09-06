# SHIFT HAPPENS — V2.5.130

Šis paketas yra lietuviška radiologijos rezidentų grafikų sistemos versija.


## V2.5.130 sąsajos pataisa

- Atskiro **„Seniūnės skydo“** nebėra.
- SP ir ŠR išplėstiniame režime turi **„Privatūs pageidavimai“**.
- Ten matoma **Nuolatinė komanda** ir **„Noriu dirbti su / Nenoriu dirbti su“**.
- Privatus langas nebekrenta dėl senesnio deploy'intame `db.py` trūkstamos V2.5.128 funkcijos.

## Kas svarbiausia šiame leidime

- Visa rezidentams ir seniūnei rodoma pagrindinė sąsaja yra lietuvių kalba.
- Paprastame režime pašalintas programuotojų žargonas: rezidentas mato aiškius laukus, pvz., **„Dirbti negaliu“**, **„Noriu laisvos“**, **„Pageidauju dirbti“**.
- Sistemos tikslas kiekvieną mėnesį — **100 % pageidavimų išpildymas**. Sudėtingame mėnesyje geriausias įmanomas rezultatas gali būti mažesnis, pavyzdžiui, 93 %, jei dalis norų tarpusavyje nesuderinami arba juos riboja svarbesnės saugos, padengimo ir darbo krūvio taisyklės.
- Pateikimo vieta 1–16 taikoma **tam pačiam grafikui** ir naudojama tik likusiam konfliktui tarp vienodai gerų sprendinių — ji nesumažina jau pasiekto bendro pageidavimų išpildymo.
- Vieša sprendimų seka: **sauga ir padengimas → 0 „Dirbti negaliu“ pažeidimų → kuo tolygesnis privalomas krūvis ir darbo vietos → maksimalus visų rezidentų pageidavimų išpildymas → pateikimo eilė tik likusiam vienodai geram konfliktui**.
- Mėnesio ciklas: pageidavimai iki 14 d. 00:00; preliminaraus grafiko parengimas iki 15 d. 00:00; apsikeitimų langas 15 d. 00:00–16 d. 00:00; nuo 16 d. 00:00 — seniūnės galutinė patikra ir galutinio grafiko paskelbimas.
- Grafikų sudarymo metodų palyginimas perkeltas į **„Tyrimas“** langą ir nebėra atskiras pagrindinės navigacijos langas.

## Seniūnės vadovas

Pagrindinis pristatymui ir kasdieniam darbui skirtas dokumentas:

`SHIFT_HAPPENS_SENIUNES_VADOVAS_V2_5_128.docx`

Trumpa tekstinė versija:

`SENIOR_USABILITY_GUIDE_LT.md`

## Paleidimas

```bash
pip install -r requirements.txt
streamlit run app.py
```

Jei naudojama ankstesnė Supabase duomenų bazė, prieš paleidžiant šį leidimą turi būti pritaikytos pakete esančios aktualios migracijos.

## Leidimo patikra

```bash
pytest -q test_v25130_release.py
```
