# core/orchestrator.py - Orchestratore dei processi di automazione
import datetime
import random
import threading
from pathlib import Path
from queue import Queue
from config.settings import Settings
from core.cache_manager import CacheManager
from core.excel_parser import stramExcel
from core.folder_builder import FolderBuilder
from scraper.browser_manager import BrowserManager
from scraper.sister_client import NavigatoreSister
from utils.istat_lookup import build_lookup
from utils.logger import get_logger
from utils.reporters import generate_report

logger = get_logger("Orchestrator")


class JobAutomazione:
    def __init__(self, riga: int, comune: str, foglio: str, particella: str, sub: str, tipo: str, chiave: str, download_job=None):
        self.riga_excel = riga
        self.comune = comune
        self.foglio = foglio
        self.particella = particella
        self.sub = sub
        self.tipo = tipo
        self.chiave = chiave
        self.download_job = download_job


class MasterOrchestrator:
    def __init__(
        self,
        control_event: threading.Event | None = None,
        status_queue: Queue | None = None,
        stop_event: threading.Event | None = None,
        office_province: str | None = None,
        input_excel: str | Path | None = None,
    ):
        self.valid_rows = []
        self.unique_jobs = []
        self.scrape_errors = []
        self.cache = CacheManager()
        self.url_ufficio_catastale = None
        self.mappa_destinazioni = {}
        self.control_event = control_event
        self.status_queue = status_queue
        self.stop_event = stop_event
        self.office_province = office_province.strip().upper() if office_province else None
        self.input_excel = Path(input_excel) if input_excel else Settings.INPUT_EXCEL
        self.total_jobs = 0
        self.processed_jobs = 0
        self.downloaded_jobs = 0
        self.cached_jobs = 0
        self.error_count = 0

    def _attendi_pausa_mimetica(self, page) -> None:
        """Inserisce una pausa casuale tra due richieste consecutive."""
        pausa_mimetica = random.uniform(
            Settings.MIN_REQUEST_PAUSE_S,
            Settings.MAX_REQUEST_PAUSE_S,
        )
        logger.info(
            f"   ⏳ Pausa mimetica: attendo {pausa_mimetica:.2f} secondi prima del prossimo record..."
        )
        page.wait_for_timeout(pausa_mimetica * 1000)

    def _send_status(self, payload: dict) -> None:
        if self.status_queue is None:
            return
        try:
            self.status_queue.put(payload, block=False)
        except Exception:
            pass

    def _send_progress(self) -> None:
        self._send_status({
            "type": "progress",
            "processed": self.processed_jobs,
            "total": self.total_jobs,
            "downloaded": self.downloaded_jobs,
            "cached": self.cached_jobs,
            "errors": self.error_count,
        })

    def _wait_for_user_action(self, prompt: str, pause_id: str) -> None:
        if self.control_event is None:
            input(prompt)
            return

        self._send_status({
            "type": "paused",
            "pause_id": pause_id,
            "message": prompt,
        })
        self.control_event.clear()

        while not self.control_event.wait(timeout=0.2):
            if self.stop_event and self.stop_event.is_set():
                self._send_status({
                    "type": "stop_requested",
                    "pause_id": pause_id,
                    "message": "Stop richiesto durante l'attesa operatore. Si procede alla fase finale...",
                })
                return

        if self.stop_event and self.stop_event.is_set():
            self._send_status({
                "type": "stop_requested",
                "pause_id": pause_id,
                "message": "Stop richiesto. Si procede alla fase finale...",
            })
            return

        self._send_status({
            "type": "resumed",
            "pause_id": pause_id,
            "message": "L'automazione è ripartita.",
        })

    def _double_check_cache(self, scrape_errors: list) -> list:
        """
        Double-check pre-report (Fase 3):
        Scorre la lista delle anomalie di scraping e verifica se il PDF
        è effettivamente presente in cache per ognuna di esse.

        - Se il PDF esiste ma l'errore era classificato come 'Errore Download':
          → aggiorna TIPO_ERRORE a 'Successo con esitazione di navigazione'
          → aggiorna DOCUMENTO_IN_CACHE a 'Sì'
        - Gli errori di parsing (senza _CHIAVE_INTERNA) sono lasciati invariati.
        - Rimuove la chiave interna di servizio _CHIAVE_INTERNA prima di restituire.
        """
        risultato = []
        for err in scrape_errors:
            chiave = err.pop("_CHIAVE_INTERNA", None)
            if chiave and self.cache.is_cached(chiave):
                tipo_originale = err.get("TIPO_ERRORE", "")
                if "Errore Download" in tipo_originale:
                    logger.warning(
                        f"   🔄 [Double-Check] PDF trovato in cache per '{chiave}'. "
                        f"Stato aggiornato: '{tipo_originale}' → 'Successo con esitazione di navigazione'."
                    )
                    err["TIPO_ERRORE"] = "Successo con esitazione di navigazione"
                    err["DOCUMENTO_IN_CACHE"] = "Sì"
            risultato.append(err)
        return risultato

    def run(self):
        """Punto di ingresso principale del workflow."""
        logger.info("=== [FASE 1] CARICAMENTO DATI LOCALI ===")
        valid_rows, raw_parsing_errors = stramExcel.parse_excel(str(self.input_excel))
        self.valid_rows = valid_rows
        self.original_headers = stramExcel.original_headers

        parsing_errors = []
        for err in raw_parsing_errors:
            err_dict = {
                "TIPO_ERRORE": err.motivo,
                "RIGA_EXCEL": err.riga_excel,
            }
            if isinstance(err.dati_originali, dict):
                err_dict.update(err.dati_originali)
            parsing_errors.append(err_dict)

        job_unici, self.mappa_destinazioni, conflitti = stramExcel.deduplicate_jobs(self.valid_rows)

        for conflitto in conflitti:
            err_dict = {
                "TIPO_ERRORE": f"Conflitto su chiave duplicata: {conflitto.chiave} ({conflitto.jobA.comune} - {conflitto.jobA.tipo} vs {conflitto.jobB.comune} - {conflitto.jobB.tipo})",
                "RIGA_EXCEL": conflitto.jobB.riga_excel,
            }
            if isinstance(conflitto.jobB.dati_originali, dict):
                err_dict.update(conflitto.jobB.dati_originali)
            parsing_errors.append(err_dict)

        duplicati = len(self.valid_rows) - len(job_unici)
        if duplicati > 0:
            parsing_errors.append({
                "TIPO_ERRORE": f"Record duplicati rilevati e accorpati: {duplicati}",
                "RIGA_EXCEL": "N/D",
            })

        for job in job_unici:
            self.unique_jobs.append(JobAutomazione(
                job.riga_excel,
                job.comune,
                job.foglio,
                job.particella,
                job.sub or "",
                job.tipo,
                job.chiave,
                download_job=job,
            ))

        logger.info(f"Righe valide: {len(self.valid_rows)} | Job unici da elaborare: {len(self.unique_jobs)}")
        self.total_jobs = len(self.unique_jobs)
        self._send_status({
            "type": "initialized",
            "total_jobs": self.total_jobs,
        })

        try:
            self._fase_download_sister()
        except Exception as fatal_error:
            logger.critical(f"Automazione interrotta o completata prematuramente: {fatal_error}")
        finally:
            logger.info("=== [FASE 3] FINALIZZAZIONE OUTPUT E REPORTING ===")

            try:
                builder = FolderBuilder(self.cache)
                builder.build(self.mappa_destinazioni)
            except Exception as ex:
                logger.error(f"Errore durante lo smistamento finale delle cartelle: {ex}")

            try:
                # Double-check pre-report: rimuove/aggiorna le anomalie
                # per cui il PDF è presente fisicamente in cache
                scrape_errors_filtrati = self._double_check_cache(self.scrape_errors)
                generate_report(parsing_errors, scrape_errors_filtrati, self.original_headers)
            except Exception as rep_err:
                logger.error(f"Errore durante la generazione del report excel: {rep_err}")

            logger.info("============================================================")
            logger.info("         Workflow terminato. Risorse salvate e consolidate!")
            logger.info("============================================================")

    def _fase_download_sister(self):
        """Fase 2: Gestisce l'automazione sequenziale su Sister con Re-Aggancio dinamico."""
        logger.info("=== [FASE 2] AVVIO AUTOMAZIONE SISTER ===")
        istat = build_lookup()

        with BrowserManager() as bm:
            page = bm.new_page()
            page.goto(Settings.SISTER_URL)

            print("\n" + "!" * 60)
            print(" AZIONI RICHIESTE ALL'OPERATORE NELLA FINESTRA DEL BROWSER:")
            print("1. Effettua il login (se richiesto).")
            print("2. Seleziona la provincia desiderata ed entra nelle Visure.")
            print("3. IMPORTANTE: Seleziona un comune per espandere il form.")
            print("4. Quando vedi a schermo i box vuoti di Foglio e Particella, FERMATI.")
            print("!" * 60 + "\n")

            self._wait_for_user_action(
                f">>> Quando sei posizionato sul FORM CATASTALE pronto, premi INVIO qui per elaborare i {len(self.unique_jobs)} job <<<",
                pause_id="initial_login",
            )

            page.wait_for_timeout(1000)
            page_reale = None

            for p in bm.context.pages:
                u = p.url.lower()
                if "login" not in u and "logout" not in u and ("sister" in u or "visure" in u or "scelta" in u):
                    page_reale = p
                    break

            if not page_reale:
                page_reale = bm.context.pages[-1]

            self.url_ufficio_catastale = page_reale.url
            logger.info(f" Finestra corretta agganciata: {self.url_ufficio_catastale}")

            fallimenti_consecutivi = 0
            contatore_lotto_reale = 0

            for idx, job in enumerate(self.unique_jobs, start=1):
                if self.stop_event and self.stop_event.is_set():
                    logger.info("Stop richiesto: terminazione anticipata della fase di scraping.")
                    self._send_status({
                        "type": "stop_requested",
                        "message": "Stop richiesto. Si procede alla fase finale...",
                    })
                    break

                logger.info(f"[{idx}/{len(self.unique_jobs)}] Elaborazione chiave: {job.chiave}")

                if self.cache.is_cached(job.chiave):
                    self.cached_jobs += 1
                    self.processed_jobs += 1
                    logger.info("   -> Job già  presente in cache (Skip).")
                    self._send_progress()
                    continue

                # CONTROLLO ANTICIPO BAN / SCADENZA SESSIONE (Ogni 50 interazioni reali)
                if contatore_lotto_reale > 0 and contatore_lotto_reale % 50 == 0:
                    logger.info(f" [BATCH LIMIT] Raggiunto il limite di {contatore_lotto_reale} record elaborati in questa sessione.")
                    print("\n" + "⚠️" * 30)
                    print("⚠️ PAUSA DI SICUREZZA - PREVENZIONE SCADENZA SESSIONE SISTER")
                    print("Per evitare l'errore di sessione scaduta dei 30 minuti, esegui queste azioni:")
                    print("1. Vai sulla finestra del browser ed effettua il LOGOUT da Sister.")
                    print("2. Effettua nuovamente il LOGIN.")
                    print("3. Entra nelle Visure e seleziona il Comune per mostrare il form vuoto.")
                    print("4. Torna qui sul terminale e premi INVIO per sbloccare il robot.")
                    print("⚠️" * 30 + "\n")

                    self._wait_for_user_action(
                        ">>> Quando sei posizionato sul modulo pronto, premi INVIO per partire con il prossimo lotto... <<<",
                        pause_id="batch_limit",
                    )

                    # 🎯 SVOLTA: Re-scansioniamo tutte le schede aperte! Il Login potrebbe aver aperto una nuova scheda
                    logger.info("Analisi delle schede del browser per intercettare la nuova sessione...")
                    page_reale = None
                    for p in bm.context.pages:
                        u = p.url.lower()
                        if "login" not in u and "logout" not in u and ("sister" in u or "visure" in u or "scelta" in u):
                            page_reale = p
                            break
                    if not page_reale:
                        page_reale = bm.context.pages[-1]

                    # Lasciamo stabilizzare la nuova scheda e i suoi frame interni
                    try:
                        page_reale.wait_for_load_state("load", timeout=5000)
                        page_reale.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    page_reale.wait_for_timeout(1500)

                    # Memorizziamo il nuovo URL valido ed azzeriamo i freni
                    self.url_ufficio_catastale = page_reale.url
                    logger.info(f"Nuova sessione agganciata stabilmente su: {self.url_ufficio_catastale}")
                    fallimenti_consecutivi = 0
                    contatore_lotto_reale = 0

                prov_list = istat.get(job.comune.upper(), [])
                if not prov_list:
                    logger.error(f"   -> Comune '{job.comune}' non censito in ISTAT.")
                    matching_rows = [r for r in self.valid_rows if r.chiave == job.chiave]
                    if matching_rows:
                        for r in matching_rows:
                            err_dict = {
                                "TIPO_ERRORE": f"Comune non censito in ISTAT: '{job.comune}'",
                                "RIGA_EXCEL": r.riga_excel,
                            }
                            if isinstance(r.dati_originali, dict):
                                err_dict.update(r.dati_originali)
                            self.scrape_errors.append(err_dict)
                    else:
                        err_dict = {
                            "TIPO_ERRORE": f"Comune non censito in ISTAT: '{job.comune}'",
                            "RIGA_EXCEL": job.riga_excel or "N/D",
                        }
                        if job.download_job and isinstance(job.download_job.dati_originali, dict):
                            err_dict.update(job.download_job.dati_originali)
                        self.scrape_errors.append(err_dict)
                    continue

                # ── BLOCCO A: Fase critica — Ricerca sul portale + Download PDF ─────────
                pdf_scaricato = False
                try:
                    if job.tipo == "NCT":
                        NavigatoreSister.search_nct(page_reale, job.comune, prov_list[0], job.foglio, job.particella)
                    else:
                        NavigatoreSister.search_ncf(page_reale, job.comune, prov_list[0], job.foglio, job.particella, job.sub or "")

                    self.cache.save_pdf(job.chiave, page_reale)
                    pdf_scaricato = True
                    self.downloaded_jobs += 1
                    self.processed_jobs += 1
                    logger.info("✅ Visura scaricata ed inserita in cache.")
                    self._send_progress()

                except Exception as e_download:
                    self.processed_jobs += 1
                    # Verifica reale: il PDF è in cache nonostante l'eccezione?
                    if self.cache.is_cached(job.chiave):
                        # Il file era già stato salvato prima del crash: non è un errore reale
                        pdf_scaricato = True
                        self.downloaded_jobs += 1
                        logger.warning(
                            f"   ⚠️ Eccezione durante il download, ma il PDF è già presente in cache. "
                            f"Job trattato come successo. Dettaglio: {e_download}"
                        )
                        self._send_progress()
                    else:
                        # Fallimento reale confermato: il documento non è stato scaricato
                        logger.error(f"   ❌ Errore di Download reale sul record [{job.chiave}]: {e_download}")
                        self.error_count += 1
                        matching_rows = [r for r in self.valid_rows if r.chiave == job.chiave]
                        if matching_rows:
                            for r in matching_rows:
                                err_dict = {
                                    "TIPO_ERRORE": f"Errore Download: {e_download}",
                                    "RIGA_EXCEL": r.riga_excel,
                                    "_CHIAVE_INTERNA": job.chiave,
                                    "DOCUMENTO_IN_CACHE": "No",
                                }
                                if isinstance(r.dati_originali, dict):
                                    err_dict.update(r.dati_originali)
                                    # Ripristina i campi di controllo dopo l'update
                                    err_dict["TIPO_ERRORE"] = f"Errore Download: {e_download}"
                                    err_dict["_CHIAVE_INTERNA"] = job.chiave
                                    err_dict["DOCUMENTO_IN_CACHE"] = "No"
                                self.scrape_errors.append(err_dict)
                        else:
                            err_dict = {
                                "TIPO_ERRORE": f"Errore Download: {e_download}",
                                "RIGA_EXCEL": job.riga_excel or "N/D",
                                "_CHIAVE_INTERNA": job.chiave,
                                "DOCUMENTO_IN_CACHE": "No",
                            }
                            if job.download_job and isinstance(job.download_job.dati_originali, dict):
                                err_dict.update(job.download_job.dati_originali)
                                err_dict["TIPO_ERRORE"] = f"Errore Download: {e_download}"
                                err_dict["_CHIAVE_INTERNA"] = job.chiave
                                err_dict["DOCUMENTO_IN_CACHE"] = "No"
                            self.scrape_errors.append(err_dict)
                        self._send_progress()

                # ── BLOCCO B: Fase non critica — Ripristino sessione + Pausa mimetica ───
                if pdf_scaricato or self.cache.is_cached(job.chiave):
                    # Il PDF è confermato in cache: il ripristino non è più un'operazione critica
                    try:
                        NavigatoreSister.torna_al_form(page_reale, self.url_ufficio_catastale)
                        fallimenti_consecutivi = 0
                        contatore_lotto_reale += 1
                        self._attendi_pausa_mimetica(page_reale)
                    except Exception as e_nav:
                        logger.error(
                            f"   ⚠️ Errore di Navigazione / Ripristino Sessione (PDF già salvato): {e_nav}"
                        )
                        # Il documento è in cache: NON è 'Documento mancante'
                        matching_rows = [r for r in self.valid_rows if r.chiave == job.chiave]
                        if matching_rows:
                            for r in matching_rows:
                                err_dict = {
                                    "TIPO_ERRORE": "Errore di Navigazione / Ripristino Sessione",
                                    "RIGA_EXCEL": r.riga_excel,
                                    "_CHIAVE_INTERNA": job.chiave,
                                    "DOCUMENTO_IN_CACHE": "Sì",
                                }
                                if isinstance(r.dati_originali, dict):
                                    err_dict.update(r.dati_originali)
                                    err_dict["TIPO_ERRORE"] = "Errore di Navigazione / Ripristino Sessione"
                                    err_dict["_CHIAVE_INTERNA"] = job.chiave
                                    err_dict["DOCUMENTO_IN_CACHE"] = "Sì"
                                self.scrape_errors.append(err_dict)
                        else:
                            err_dict = {
                                "TIPO_ERRORE": "Errore di Navigazione / Ripristino Sessione",
                                "RIGA_EXCEL": job.riga_excel or "N/D",
                                "_CHIAVE_INTERNA": job.chiave,
                                "DOCUMENTO_IN_CACHE": "Sì",
                            }
                            if job.download_job and isinstance(job.download_job.dati_originali, dict):
                                err_dict.update(job.download_job.dati_originali)
                                err_dict["TIPO_ERRORE"] = "Errore di Navigazione / Ripristino Sessione"
                                err_dict["_CHIAVE_INTERNA"] = job.chiave
                                err_dict["DOCUMENTO_IN_CACHE"] = "Sì"
                            self.scrape_errors.append(err_dict)
                        fallimenti_consecutivi += 1
                        contatore_lotto_reale += 1
                        try:
                            self._attendi_pausa_mimetica(page_reale)
                        except Exception:
                            pass
                else:
                    # Download fallito: tentativo di ripristino silenzioso, senza aggiungere ulteriori errori
                    try:
                        NavigatoreSister.torna_al_form(page_reale, self.url_ufficio_catastale)
                        fallimenti_consecutivi = 0
                    except Exception as reset_error:
                        logger.error(f"   Impossibile ripristinare il modulo dopo download fallito: {reset_error}")
                        fallimenti_consecutivi += 1
                    contatore_lotto_reale += 1
                    try:
                        self._attendi_pausa_mimetica(page_reale)
                    except Exception:
                        pass

                if fallimenti_consecutivi >= 4:
                    logger.critical("Rilevati 4 disallineamenti strutturali consecutivi del browser!")
                    raise RuntimeError("Interruzione preventiva di sicurezza: browser de-sincronizzato.")

            # [FASE 2.4] ATTESA TIMERIZZATA PER COSTRUIRE I DOCUMENTI CATASTALI ASINCRONI
            print("\n" + "⏳" * 30)
            logger.info("=== [FASE 2.4] INIZIO ATTESA ELABORAZIONE ATTI DIFFERITI (20 MINUTI) === \n ALTRIMENTI FAI IL LOGOUT E CHIUDI LA FINESTRA DEL BROWSER")
            minuti_totali_attesa = 20  # Modificabile a 20 se necessario

            for minuto in range(minuti_totali_attesa, 0, -1):
                logger.info(f"⏱️ Sister sta elaborando i KO asincroni sullo sfondo... Mancano {minuto} minuti al recupero.")
                # Mantiene sveglia la connessione simulando micro-attività di Playwright ad ogni minuto
                page_reale.wait_for_timeout(60 * 1000)
            print("⏳" * 30 + "\n")

            # 🎯 [FASE 2.5] AVVIO RACCOLTA DIFFERITA DALLA TABELLA RICHIESTE
            logger.info("=== [FASE 2.5] AVVIO RACCOLTA DIFFERITA VISURE SOSPESE ===")
            try:
                NavigatoreSister.recupera_richieste_differite(page_reale, self.cache)
            except Exception as e_richieste:
                logger.error(f"Errore durante l'estrazione automatica dal pannello Richieste: {e_richieste}")

            # 🎯 [FASE 2.6] LOGOUT CONTROLLATO PER LIBERARE LO SLOT SUL SERVER
            logger.info("=== [FASE 2.6] ESECUZIONE LOGOUT CONTROLLATO UTENTE ===")
            try:
                logout_eseguito = False
                # Cerca l'ancora o il bottone Esci sia nella pagina radice che nei sotto-frame
                for frame in page_reale.frames:
                    btn_esci = frame.locator("a:has-text('Esci'), button:has-text('Esci'), a[href*='logout'], a[href*='LogOut']").first
                    if btn_esci.count() > 0:
                        btn_esci.click()
                        logout_eseguito = True
                        break
                if not logout_eseguito:
                    btn_esci_root = page_reale.locator("a:has-text('Esci'), button:has-text('Esci'), a[href*='logout']").first
                    if btn_esci_root.count() > 0:
                        btn_esci_root.click()
                logger.info("✅ Tasto 'Esci' intercettato con successo. Slot liberato sul server Sogei.")
                page_reale.wait_for_timeout(2000)
            except Exception as e_logout:
                logger.error(f"⚠️ Impossibile completare il logout controllato automatico: {e_logout}")