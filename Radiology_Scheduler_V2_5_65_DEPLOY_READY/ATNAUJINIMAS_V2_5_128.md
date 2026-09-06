# V2.5.128 — pristatymo ir taisyklių suvienodinimas

## Vieša taisyklių logika

Sistemos pristatyme ir seniūnės vadove naudojama viena aiški sprendimų seka:

1. Saugumas, įmanomumas ir privalomas padengimas.
2. „Dirbti negaliu“ — 0 pažeidimų.
3. Kuo tolygesnis privalomo krūvio ir darbo vietų paskirstymas.
4. Maksimalus visų rezidentų pageidavimų išpildymas — tikslas 100 %.
5. Pateikimo eilė 1–16 tik tada, kai lieka keli vienodai geri, bet tarpusavyje nesuderinami variantai.

Pavyzdžiui, sudėtingame mėnesyje geriausias įmanomas pageidavimų rezultatas gali būti 93 %. Sistema pirmiausia išsaugo tą geriausią bendrą rezultatą, o pateikimo vietą naudoja tik likusiam vienodai geram konfliktui.

## Vartotojo sąsaja

- Paprastame rezidento režime palikti tik aiškūs kasdieniai pavadinimai.
- Techniniai sprendiklio terminai nerodomi ten, kur rezidentui jų nereikia.
- Pagrindinė vartotojo sąsaja lietuviška.
- Grafikų sudarymo metodų palyginimas yra „Tyrimas“ lange, o ne atskiroje pagrindinės navigacijos skiltyje.

## Grafiko uždarymo ciklas

- Iki 14 d. 00:00 — pageidavimų pateikimas.
- 14 d. 00:00–15 d. 00:00 — seniūnės generavimas, patikra ir preliminaraus grafiko paskelbimas.
- 15 d. 00:00–16 d. 00:00 — 24 val. apsikeitimų langas.
- Nuo 16 d. 00:00 — rezidentų savitarna užrakinta; seniūnė atlieka galutinę rankinę patikrą ir paskelbia galutinį grafiką.

## Sprendinio stabilumas

Kai sistema jau rado maksimalų bendrą pageidavimų rezultatą, vėlesni vienodai gerų variantų pasirinkimai negali jo sumažinti.
