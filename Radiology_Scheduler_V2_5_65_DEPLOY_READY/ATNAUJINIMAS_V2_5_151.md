# RAPA V2.5.151 — HARD-aware Friday water-fill

## Kas sutvarkyta

1. **`Negaliu dirbti` nebekonfliktuoja su aklu penktadienių 0–1 floor/ceil.**
   Penktadienių water-fill dabar skaičiuoja kiekvieno rezidento realią HARD tinkamumo talpą. Jei žmogus keturis iš penkių penktadienių negali dirbti, sistema jo nebeverčia gauti tokio pat penktadienio krūvio kaip pilnai tinkami rezidentai. Likęs krūvis water-fill'inamas tarp tinkamų žmonių.
2. **0 Resident-HARD pažeidimų išlieka publikavimo sąlyga.** Fairness negali nusipirkti `Negaliu dirbti` pažeidimo.
3. **Sutvarkytas V2.5.141 account-mode refinement crashas.** Kompaktiškas two-phase MILP builder dabar priima named constraint argumentą kaip legacy builder.
4. **Sudarymas aiškiai rodo mėnesį, kiek žmonių pateikė pageidavimus ir ar DB turi juodraštį.**
5. **V2.5.150 legacy draft compatibility guard paliktas.** Senas netinkamas DB draftas nėra naudojamas kaip gerinimo bazė.

## Deploy
Keisti **app.py + scheduler_engine.py kartu**. Naujos Supabase migracijos šiam pataisymui nereikia.
