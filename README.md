# Scarica Visure

Automazione Python per scaricare visure catastali da Sister e organizzare i PDF in un albero di output strutturato.

## Panoramica

Il progetto legge un file Excel di input (`data/input/piano particellare.xlsx`), normalizza i dati catastali, esegue il download delle visure tramite browser Playwright e smista i PDF in `data/output_tree` secondo la logica di destinazione definita in Excel.

## Requisiti

- Python 3.11+ (o versione compatibile con le librerie usate)
- `venv` o ambiente virtuale Python
- Connessione a Internet per accedere al portale Sister
- Login manuale a Sister tramite browser
- File `scraper/state/state.json` presente: il programma richiede questo file all'avvio e non lo genera automaticamente
- File `utils/Elenco-comuni-italiani.csv` presente per il lookup ISTAT

## Dipendenze

Le dipendenze sono elencate in `requirements.txt`:

- playwright
- openai
- pandas
- openpyxl
- pydantic
- pydantic-settings
- ddddocr
- pytest
- pytest-playwright

## Installazione

1. Crea e attiva un ambiente virtuale Python.
2. Installa le dipendenze:

```powershell
pip install -r requirements.txt
```

3. Inizializza Playwright se non ancora fatto:

```powershell
playwright install
```

## Configurazione

Il file `config/settings.py` definisce costanti e percorsi locali.

- `INPUT_EXCEL` punta a `data/input/piano particellare.xlsx`
- `CACHE_DIR` è `data/cache`
- `OUTPUT_DIR` è `data/output_tree`
- `ISTAT_CSV` è `utils/Elenco-comuni-italiani.csv`
- `STATE_FILE` è `scraper/state/state.json`
- `LOG_FILE` è `sister.log`

La variabile di ambiente `OPENAI_API_KEY` è utilizzata da `scraper/sister_client.py` per il riconoscimento automatico del captcha.

> Nota: il file `scraper/state/state.json` deve esistere prima dell'avvio. Se non esiste, il programma termina immediatamente con un errore.

## Uso

Esegui lo script principale:

```powershell
python main.py
```

### Flusso di esecuzione

1. Caricamento e parsing dell'Excel
2. Deduplicazione dei job e costruzione della mappa di destinazione
3. Avvio browser Playwright con stato di sessione esistente
4. Richiesta al'operatore di effettuare il login manuale e posizionarsi sul form di Sister
5. Esecuzione sequenziale dei download delle visure
6. Recupero delle richieste differite al termine della prima fase
7. Smistamento dei PDF dalla cache alla cartella `data/output_tree`
8. Generazione di un report Excel delle eccezioni

## Struttura del progetto

- `main.py` - entrypoint principale
- `config/settings.py` - impostazioni e percorsi
- `core/orchestrator.py` - orchestratore workflow
- `core/excel_parser.py` - parsing e deduplicazione Excel
- `core/cache_manager.py` - gestione cache PDF
- `core/folder_builder.py` - costruzione dell'albero di output
- `scraper/browser_manager.py` - gestione Playwright e sessioni
- `scraper/sister_client.py` - automazione delle ricerche su Sister
- `utils/logger.py` - configurazione logging
- `utils/reporters.py` - generazione report anomalie
- `utils/istat_lookup.py` - lookup ISTAT da CSV
- `model/po/rigaExcel.py` - dataclass per job e righe invalide

## Note importanti

- Il progetto richiede l'accesso reale a Sister e un browser visibile (`HEADLESS=False`).
- L'automazione dipende dai selettori e dall'interfaccia di Sister; modifiche al portale possono interrompere il funzionamento.
- La risoluzione del captcha utilizza OpenAI; se `OPENAI_API_KEY` non è configurata, la procedura può fallire.
- Il file Excel deve contenere colonne riconosciute dal parser, come `Comune`, `Foglio`, `Particella`, `Tipo`, `Sub`, `Opera`, `Categoria`.
- Il file `scraper/state/state.json` deve essere presente al momento dell'esecuzione: il programma non lo crea automaticamente.
- Dopo circa 50 ricerche reali, il programma richiederà un logout/login manuale su Sister per evitare la scadenza della sessione.
- Se Sister restituisce una schermata rossa di errore durante la ricerca, il record viene saltato e successivamente recuperato dalla sezione "Richieste".

## Test

Esegui i test unitari con:

```powershell
pytest
```
