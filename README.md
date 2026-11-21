# Auto elettriche in Italia (listino Quattroruote)

Raccoglie tutti gli allestimenti **solo BEV** e produce `data/ev_ita.csv` (apribile in Excel), `data/ev_ita.json`
e `index.html` (tabella ordinabile e filtrabile, righe gialle = esaurimento scorte).

## Opzione A – su GitHub (consigliata)
1. Crea un repository su github.com e carica tutti questi file (Add file → Upload files; la cartella `.github` va caricata con la sua struttura).
2. Scheda **Actions** → "Aggiorna tabella EV" → **Run workflow**. Prima volta: lancia pure `scrape.py --models tesla/model-3` modificando temporaneamente il comando nel file `.github/workflows/aggiorna.yml` per fare una prova da 1 minuto.
3. A fine corsa trovi i file aggiornati nel repository. Poi parte da solo il 1° di ogni mese.
4. Per vedere la pagina: Settings → Pages → Branch `main` / root.
Se qualcosa non va, scarica l'artefatto **debug** dalla pagina della corsa: contiene l'HTML grezzo.

## Opzione B – sul tuo PC
```
pip install -r requirements.txt
playwright install chromium
python scrape.py --models tesla/model-3 dacia/spring --debug   # prova rapida
python scrape.py                                               # tutto il listino
```
Poi apri `index.html` con doppio clic.

## Note
- Gli allestimenti sono considerati BEV solo se la loro scheda ha capacità batteria e nessun riferimento a ibrido/termico nella sezione Motore. Quelli esclusi sono in `data/scartate.csv`.
- Autonomia: valore del sito se presente, altrimenti capacità/consumo×100 (colonna `autonomia_fonte`).
- Anno: ricavato dal codice finale dell'URL.
- Pausa di 1,5 s tra le richieste (`--delay`).
