# V2.5.130 — privatūs blokai ir švari navigacija

- „Seniūnės skydas“ visiškai pašalintas iš navigacijos; jo atskiro lango nebėra.
- Pageidavimų pateikimo būklė lieka jau esančioje „Pageidavimų“ skiltyje.
- SP ir ŠR „Išplėstiniame“ režime turi atskirą „Privatūs pageidavimai“ langą.
- Jame aiškiai rodomi „Nuolatinė komanda“ ir „Noriu dirbti su / Nenoriu dirbti su“ blokai.
- ŠR mato bendrus komandos nustatymus; juos redaguoja SP. Asmeninius „dirbti su / nedirbti su“ pageidavimus SP ir ŠR pildo atskirai.
- Privatūs porų pageidavimai turi suderinamumo sluoksnį: aplikacija nebekrenta su `AttributeError`, jei deploy'e dar likęs senesnis `db.py`.
- Jei V2.5.128 lentelė dar nesukurta, langas atsiveria; išsaugant pateikiama aiški migracijos žinutė vietoje visos aplikacijos griūties.
- Privatus langas vizualiai sutrumpintas: pašalinti pertekliniai aiškinamieji blokai, rezultatas suskleistas.
