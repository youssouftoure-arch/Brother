# core/cache_manager.py — Check e salvataggio delle visure PDF in cache
from pathlib import Path
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
            with page.expect_download(timeout=Settings.DOWNLOAD_TIMEOUT_MS) as dl_info:
                target_clickable.locator(Settings.SEL_DOWNLOAD_PDF).click(timeout=5000)
            
            download = dl_info.value
            download.save_as(str(dest))
            return dest
            
        except Exception as e:
            # 🎯 TRASFORMAZIONE ERRORE: Impedisce ai timeout nativi di rompere l'orchestratore
            raise SisterError(f"Impossibile completare il download del PDF (Documentazione non disponibile o schermata imprevista). Dettaglio: {e}")