# core/cache_manager.py — Check e salvataggio delle visure PDF in cache
from datetime import datetime
from pathlib import Path
import time as ptime
from config.settings import Settings
from utils.logger import get_logger
from scraper.sister_client import SisterError

logger = get_logger("CacheManager")

class CacheManager:
    def __init__(self):
        Settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def is_cached(self, chiave: str) -> bool:
        return (Settings.CACHE_DIR / f"{chiave}.pdf").exists()

    def get_path(self, chiave: str) -> Path:
        return Settings.CACHE_DIR / f"{chiave}.pdf"

    def save_pdf(self, chiave: str, page) -> Path:
        """Intercetta il download generato da Sister cercando il tasto nei frame visibili."""
        dest = self.get_path(chiave)
        logger.info(f"Intercettazione del download per la visura: {chiave}")
        
        target_clickable = page
        for frame in page.frames:
            if frame.locator(Settings.SEL_DOWNLOAD_PDF).count() > 0:
                target_clickable = frame
                break
        
        try:
            # 🟢 STRATEGIA ANTI-LAG SOGEI PER DOWNLOAD PESANTI
            btn_pdf = target_clickable.locator(Settings.SEL_DOWNLOAD_PDF)

            try:
                logger.info("⏳ Sister sta elaborando il documento... Aspetto che il pulsante PDF sia visibile (Fino a 20s)...")
                # 1. Aspetta in modo asincrono che il bottone appaia effettivamente a schermo
                btn_pdf.wait_for(state="visible", timeout=20000)
                ptime.sleep(0.6)  # Micro-pausa mimetica: l'operatore umano vede il tasto e si sposta col mouse
            except Exception as e_visible:
                logger.error("❌ Il tasto PDF non è apparso entro 20 secondi. Sister è in sovraccarico critico.")
                raise e_visible

            # 2. Avvio del download con i rubinetti dei timeout completamente aperti
            logger.info("🎯 Pulsante visibile! Inizio l'intercettazione del flusso del file...")
            
            # Portiamo l'attesa del download a 30 secondi (30000ms) per dare tempo a Sogei di fare lo streaming del PDF
            with page.expect_download(timeout=30000) as dl_info:
                # Diamo 10 secondi al click per registrarsi sul server rallentato
                btn_pdf.click(timeout=10000)
            
            download = dl_info.value
            download.save_as(str(dest))
            return dest
            
        except Exception as e:
            # 🎯 TRASFORMAZIONE ERRORE: Impedisce ai timeout nativi di rompere l'orchestratore
            raise SisterError(f"Impossibile completare il download del PDF (Documentazione non disponibile o schermata imprevista). Dettaglio: {e}")