"""Orchestrazione della raccolta dati e delle visure storiche da Sister."""

from __future__ import annotations

import random
import threading
from pathlib import Path
from queue import Queue

from config.settings import Settings
from core.cache_manager import CacheManager
from core.historical_workbook import HistoricalJob, HistoricalWorkbook
from scraper.browser_manager import BrowserManager
from scraper.sister_client import CaptchaServiceUnavailable, NavigatoreSister
from utils.logger import get_logger
from utils.reporters import generate_report

logger = get_logger("Orchestrator")


class MasterOrchestrator:
    def __init__(
        self,
        control_event: threading.Event | None = None,
        status_queue: Queue | None = None,
        stop_event: threading.Event | None = None,
        office_province: str | None = None,
        input_excel: str | Path | None = None,
    ):
        self.control_event = control_event
        self.status_queue = status_queue
        self.stop_event = stop_event
        self.office_province = office_province.strip().upper() if office_province else None
        self.input_excel = Path(input_excel) if input_excel else Settings.INPUT_EXCEL
        self.cache = CacheManager()
        self.scrape_errors: list[dict] = []
        self.total_jobs = 0
        self.processed_jobs = 0
        self.downloaded_jobs = 0
        self.cached_jobs = 0
        self.error_count = 0

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
        self._send_status({"type": "paused", "pause_id": pause_id, "message": prompt})
        self.control_event.clear()
        while not self.control_event.wait(timeout=0.2):
            if self.stop_event and self.stop_event.is_set():
                return
        self._send_status({
            "type": "resumed",
            "pause_id": pause_id,
            "message": "L'automazione è ripartita.",
        })

    def _attendi_pausa_mimetica(self, page) -> None:
        pausa = random.uniform(Settings.MIN_REQUEST_PAUSE_S, Settings.MAX_REQUEST_PAUSE_S)
        logger.info(f"   ⏳ Pausa mimetica: {pausa:.2f} secondi prima del prossimo record...")
        page.wait_for_timeout(pausa * 1000)

    @staticmethod
    def _page_sister(context):
        for page in context.pages:
            url = page.url.lower()
            if "login" not in url and "logout" not in url and (
                "sister" in url or "visure" in url or "scelta" in url
            ):
                return page
        return context.pages[-1]

    @staticmethod
    def _wait_page_stable(page) -> None:
        try:
            page.wait_for_load_state("load", timeout=5000)
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

    def _record_error(self, job: HistoricalJob, exc: Exception, pdf_cached: bool) -> None:
        self.scrape_errors.append({
            "TIPO_ERRORE": str(exc),
            "RIGA_EXCEL": job.source_row,
            "DOCUMENTO_IN_CACHE": "Sì" if pdf_cached else "No",
            "n. Ordine": job.order,
            "Comune": job.comune,
            "Foglio": job.foglio,
            "Particella": job.particella,
        })

    def run(self) -> None:
        logger.info("=== [FASE 1] LETTURA PIANO PARTICELLARE STORICO ===")
        workbook = HistoricalWorkbook(self.input_excel)
        jobs = workbook.jobs()
        self.total_jobs = len(jobs)
        workbook.build_destination(jobs)
        logger.info(f"Righe catastali da elaborare: {self.total_jobs}")
        self._send_status({"type": "initialized", "total_jobs": self.total_jobs})

        try:
            self._fase_sister(workbook, jobs)
        except Exception as fatal_error:
            logger.critical(f"Automazione interrotta o completata prematuramente: {fatal_error}")
        finally:
            logger.info("=== [FASE 3] CONSOLIDAMENTO OUTPUT ===")
            try:
                workbook.build_destination(jobs)
                for job in jobs:
                    cached_pdf = self.cache.get_path(job.cache_key)
                    if cached_pdf.exists():
                        workbook.publish_pdf(job, cached_pdf)
                logger.info(f"✅ File di destinazione aggiornato: {workbook.output}")
            except Exception as exc:
                logger.error(f"Errore durante il consolidamento dell'output: {exc}")
            try:
                generate_report([], self.scrape_errors)
            except Exception as exc:
                logger.error(f"Errore durante la generazione del report eccezioni: {exc}")
            logger.info("=== Workflow visure storiche terminato ===")

    def _fase_sister(self, workbook: HistoricalWorkbook, jobs: list[HistoricalJob]) -> None:
        logger.info("=== [FASE 2] AVVIO AUTOMAZIONE SISTER STORICA ===")
        with BrowserManager() as browser_manager:
            page = browser_manager.new_page()
            page.goto(Settings.SISTER_URL)

            print("\n" + "!" * 68)
            print(" AZIONI RICHIESTE NEL BROWSER:")
            print("1. Effettua il login a Sister.")
            print("2. Entra in Ricerca per immobile nell'ufficio di Mantova.")
            print("3. Fermati sul form iniziale con Comune, Sezione, Foglio e Particella.")
            print("!" * 68 + "\n")
            self._wait_for_user_action(
                f">>> Quando il form è pronto, premi INVIO per elaborare {len(jobs)} particelle <<<",
                "initial_login",
            )
            if self.stop_event and self.stop_event.is_set():
                return

            page = self._page_sister(browser_manager.context)
            self._wait_page_stable(page)
            initial_url = page.url
            logger.info(f"Pagina iniziale agganciata: {initial_url}")
            NavigatoreSister._aggancia_form_ricerca_storica(page)

            real_interactions = 0
            consecutive_failures = 0

            for index, job in enumerate(jobs, start=1):
                if self.stop_event and self.stop_event.is_set():
                    logger.info("Stop richiesto: consolidamento dei risultati già raccolti.")
                    break

                logger.info(
                    f"[{index}/{len(jobs)}] Ordine {job.order}: "
                    f"{job.comune} FG {job.foglio} PART {job.particella} "
                    f"SEZ {job.sezione or '-'}"
                )
                cached_pdf = self.cache.get_path(job.cache_key)
                if workbook.has_result(job) and cached_pdf.exists():
                    workbook.publish_pdf(job, cached_pdf)
                    self.cached_jobs += 1
                    self.processed_jobs += 1
                    logger.info("   -> Dati e visura storica già in cache (Skip).")
                    self._send_progress()
                    continue

                if real_interactions and real_interactions % 50 == 0:
                    logger.info("[BATCH LIMIT] 50 record reali completati: richiesta nuova sessione.")
                    print("\n" + "⚠️" * 30)
                    print("Effettua LOGOUT, nuovo LOGIN e torna al form Ricerca per immobile.")
                    print("⚠️" * 30 + "\n")
                    self._wait_for_user_action(
                        ">>> Quando il form iniziale è nuovamente pronto, premi INVIO <<<",
                        "batch_limit",
                    )
                    if self.stop_event and self.stop_event.is_set():
                        break
                    page = self._page_sister(browser_manager.context)
                    self._wait_page_stable(page)
                    initial_url = page.url
                    NavigatoreSister._aggancia_form_ricerca_storica(page)
                    consecutive_failures = 0
                    real_interactions = 0

                success = False
                stop_for_captcha_service = False
                try:
                    result = NavigatoreSister.search_historical_property(page, job)
                    result.intestatari = NavigatoreSister.open_owners(page)
                    workbook.save_result(job, result)
                    logger.info(
                        f"   ✅ Dati catastali e {len(result.intestatari)} intestatari salvati in cache."
                    )

                    if not cached_pdf.exists():
                        NavigatoreSister.request_historical_analytical(page, job)
                        cached_pdf = self.cache.save_pdf(job.cache_key, page)
                        self.downloaded_jobs += 1
                    else:
                        self.cached_jobs += 1

                    workbook.publish_pdf(job, cached_pdf)
                    success = True
                    consecutive_failures = 0
                    logger.info(f"✅ Visura storica salvata come {job.pdf_name}")
                except Exception as exc:
                    self.error_count += 1
                    consecutive_failures += 1
                    stop_for_captcha_service = isinstance(exc, CaptchaServiceUnavailable)
                    logger.error(f"   ❌ Errore sull'ordine {job.order}: {exc}")
                    self._record_error(job, exc, cached_pdf.exists())
                finally:
                    self.processed_jobs += 1
                    real_interactions += 1
                    self._send_progress()

                try:
                    NavigatoreSister.return_to_historical_search(page, initial_url)
                except Exception as reset_error:
                    logger.error(f"   ❌ Ripristino del form fallito: {reset_error}")
                    if success:
                        consecutive_failures += 1
                        self._record_error(job, reset_error, cached_pdf.exists())

                try:
                    self._attendi_pausa_mimetica(page)
                except Exception:
                    pass

                if stop_for_captcha_service:
                    logger.critical(
                        "Automazione fermata dopo il primo errore Vision: "
                        "verificare credito e quota della API key OpenAI."
                    )
                    break

                if consecutive_failures >= 4:
                    raise RuntimeError("Interruzione preventiva: browser disallineato per 4 record consecutivi.")

            self._logout(page)

    @staticmethod
    def _logout(page) -> None:
        logger.info("=== LOGOUT CONTROLLATO SISTER ===")
        try:
            for frame in list(page.frames):
                button = frame.locator(
                    "a:has-text('Esci'), button:has-text('Esci'), "
                    "a[href*='logout' i]"
                )
                if button.count():
                    button.first.click()
                    page.wait_for_timeout(2000)
                    logger.info("✅ Logout completato.")
                    return
            logger.warning("Tasto Esci non trovato: completare il logout manualmente.")
        except Exception as exc:
            logger.error(f"Logout automatico non completato: {exc}")
