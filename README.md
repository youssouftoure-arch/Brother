# Brother — visure storiche

Automazione Playwright per raccogliere da Sister i dati catastali e gli intestatari,
aggiornare una copia del piano particellare e scaricare le visure storiche analitiche.

## Input e output

L'input è un file `.xlsx` con le colonne:

- `n. Ordine`
- `Ditte catastali o Proprietario ed indirizzo`
- `Comune`
- `foglio`, `particelle`, `sub`
- `ha`, `are`, `cent.`, `MQ`
- `Qualità terreno categoria`
- `Reddito Dom.`, `Reddito Agr.`

Il sorgente non viene modificato. L'output viene creato così:

```text
output/
├── destinazione.xlsx
├── storica/
│   └── <ordine>_<comune>_<foglio>_<particella>.pdf
└── report_eccezioni_<timestamp>.xlsx   # soltanto in presenza di errori
```

Per ogni immobile il primo intestatario resta sulla riga numerata. Gli eventuali
intestatari successivi vengono inseriti subito sotto su righe `a`, `b`, `c` e così
via. Le altre celle di queste righe restano vuote.

`MQ` viene calcolato da Python con:

```text
MQ = ha × 10.000 + are × 100 + centiare
```

## Flusso Sister

1. L'operatore effettua il login, entra nell'ufficio di Mantova e apre il form
   `Ricerca per immobile`.
2. Brother seleziona Comune, eventuale Sezione, Foglio e Particella e preme
   `Ricerca`.
3. Se compare la conferma per l'assenza del subalterno, preme `Conferma`.
4. Legge la prima riga dell'`Elenco Immobili`, limitandosi alle colonne presenti
   nell'Excel.
5. Apre `Intestati` e conserva ogni riga completa, oppure registra zero
   intestatari soltanto quando Sister lo dichiara esplicitamente.
6. Torna all'elenco, apre `Visura Per Immobile`, seleziona
   `Storica - Analitica`, gestisce il codice di sicurezza e preme `Inoltra`.
7. Attende il pulsante `Salva`, intercetta il download e ritorna al form iniziale.

La sezione è `B` per Borgocarbonara. Le righe di `Sermide e Felonica` vengono
elaborate senza sezione.

## Affidabilità e cache

- Browser visibile, stato di sessione, mascheramento Playwright e radar sugli
  iframe restano quelli della versione collaudata.
- Sono mantenute le pause casuali, le attese anti-lag del download, due tentativi
  per il codice di sicurezza e la nuova autenticazione ogni 50 richieste reali.
- I PDF vengono conservati in `data/cache` con una chiave che include ordine,
  Comune, Foglio e Particella.
- I dati testuali vengono salvati in JSON sotto `data/cache/dati_storici`.
- Un record viene saltato al riavvio soltanto quando dati e PDF sono entrambi in
  cache. Il pulsante dell'interfaccia per svuotare la cache rimuove entrambi.

## Avvio

```powershell
python main.py
```

Dall'interfaccia selezionare il piano particellare `.xlsx`, impostare la chiave
OpenAI e avviare. Quando il form Sister è pronto, usare il pulsante di sblocco.

## Test

```powershell
pytest -q tests/test_historical_workbook.py core/test_excel_parser.py
```
