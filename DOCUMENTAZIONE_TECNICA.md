# Documentazione tecnica

## Obiettivo

Questo progetto automatizza il download di visure catastali dal portale Sister, partendo da un file Excel di input. Il risultato è una raccolta di file PDF organizzati in un albero di output con struttura cliente.

## Architettura

Il flusso complessivo è gestito da `main.py` e dall'orchestratore `core/orchestrator.py`.

### Componenti principali

- `main.py`
  - Punto di ingresso dell'applicazione.
  - Inizializza `MasterOrchestrator` e avvia `engine.run()`.

- `config/settings.py`
  - Carica variabili d'ambiente da `.env` se presente.
  - Definisce percorsi locali, URL di Sister, timeout e selettori Playwright.

- `core/orchestrator.py`
  - Legge i dati Excel e li normalizza.
  - Deduplica i job e costruisce la mappa delle destinazioni.
  - Avvia l'automazione browser su Sister.
  - Esegue il build dell'albero di output e la generazione del report finale.

- `core/excel_parser.py`
  - `stramExcel._load_df()`: carica l'Excel con header sulla riga 1 o, in fallback, sulla riga 0.
  - `parse_excel()`: normalizza i valori, scarta righe invalide e crea oggetti `DownloadJob`.
  - `deduplicate_jobs()`: aggrega i job con chiavi duplicate e rileva conflitti di metadati.
  - `DownloadJob.chiave` è costruita come `COMUNE_FOGLIO_PARTICELLA[_SUB]_TIPO`.

- `model/po/rigaExcel.py`
  - `DownloadJob`: dataclass che definisce il job di download.
  - `rigaInvalida`: memorizza righe Excel scartate e motivazione.
  - `jobConflictWarning`: rappresenta conflitti tra job con stessa chiave ma metadati diversi.

- `scraper/browser_manager.py`
  - Gestisce il ciclo di vita di Playwright.
  - Usa `scraper/state/state.json` come `storage_state` per riutilizzare la sessione.
  - In caso di crash mantiene il browser aperto per consentire il logout manuale.

- `scraper/sister_client.py`
  - `NavigatoreSister._compila_modulo_unificato()`: compila il form di ricerca per NCT/NCF.
  - `NavigatoreSister._risolvi_captcha_automatico()`: usa OpenAI GPT-4o-mini per decodificare il captcha immagine.
  - `NavigatoreSister._processa_ricerca_con_retry()`: esegue la ricerca, gestisce captcha e controlla errori applicativi.
  - `NavigatoreSister.torna_al_form()`: ripristina il form di input dopo ogni ricerca.
  - `NavigatoreSister.recupera_richieste_differite()`: scarica visure differite dalla sezione "Richieste".

- `core/cache_manager.py`
  - Salva i PDF scaricati nella cache (`data/cache`).
  - Intercetta il pulsante di download all'interno dei frame della pagina.

- `core/folder_builder.py`
  - Costruisce l'albero `data/output_tree` in base alla mappa `destinazioni`.
  - Normalizza i nomi delle cartelle per rimuovere caratteri di ritorno a capo.
  - Rinomina i file con l'uso della provincia ISTAT e copia i PDF dalla cache.

- `utils/logger.py`
  - Configura logger con handler console e file.
  - Scrive su `sister.log` con livello DEBUG e su console con livello INFO.

- `utils/reporters.py`
  - Crea un report Excel delle eccezioni in `data/output_tree`.
  - Unisce errori di parsing e errori di scraping.

- `utils/istat_lookup.py`
  - Carica il CSV `utils/Elenco-comuni-italiani.csv`.
  - Costruisce un lookup delle province per nome comune.

## Dettagli funzionali

### Parsing Excel

- Riconosce colonne con nomi variabili (es. `Opera`, `opera`, `opere `).
- Ignora righe con valori "NAN" o "NONE".
- Scarta tipologie non supportate come `FOSSO`, `CANALE`, `STRADA`.
- Normalizza i tipi catastali in `NCT` o `NCF`.
- Accetta `Sub` o `Porzione` come subalterno.

### Deduplicazione

- Le chiavi duplicate vengono accorpate e la mappa destinazione conserva tutte le possibili destinazioni.
- Viene segnalato un conflitto di metadati se due job con la stessa chiave hanno campi catastali diversi.

### Automazione browser

- Richiede un login manuale iniziale su Sister.
- Usa Playwright con sessione memorizzata in `scraper/state/state.json`.
- Cerca di mantenere il browser sincronizzato anche dopo errori di pagina.
- Dopo 50 job eseguiti richiede all'operatore un logout/login per evitare scadenza di sessione.
- Attende 15 minuti per raccogliere richieste differite e poi le scarica.

### Download e cache

- Il PDF viene salvato in `data/cache/<chiave>.pdf`.
- Se un job è già presente in cache viene saltato.
- La copia finale in `data/output_tree` avviene solo se il PDF esiste in cache.

### Output

- Il file finale viene rinominato in base a `Provincia-Comune-Foglio-Particella[-Sub].pdf`.
- Il percorso di destinazione viene costruito a partire dal campo `opera` e `categoria`.
- Alcune regole di smistamento mappano i testi a sottocartelle quali `cabine`, `opere di invarianza idraulica`, `strade accesso esistenti`, ecc.

## Percorsi di file chiave

- Input Excel: `data/input/piano particellare.xlsx`
- Cache PDF: `data/cache`
- Output strutturato: `data/output_tree`
- Stato browser: `scraper/state/state.json`
- Log: `sister.log`
- Report di eccezioni: `data/output_tree/report_eccezioni_<timestamp>.xlsx`

## Limitazioni note

- L'automazione è fortemente dipendente dalla struttura HTML del portale Sister.
- La funzione captcha automatico richiede una chiave OpenAI valida.
- Il modulo di login è manuale; non è presente un login automatico completo nel codice.
- `scraper/state/state.json` non deve esistere prima dell'esecuzione; il programma lo crea automaticamente.
- Se `utils/Elenco-comuni-italiani.csv` manca, il software non può operare.
- Dopo 50 ricerche reali, Sister può richiedere un logout/login per compensare la durata limitata della sessione.
- In caso di schermata rossa di errore da Sister, il record viene saltato e poi ripreso dalla sezione "Richieste".

## Testing

- `core/test_excel_parser.py` contiene test unitari per il parser Excel.
- Usa `pytest` per l'esecuzione.

## Presupposti di esecuzione

- Browser visibile e sessione valida.
- Form Catastale correttamente posizionato prima dell'avvio.
- Input Excel con colonne riconosciute dal parser.
- Ambiente Python attivo con tutte le dipendenze installate.
