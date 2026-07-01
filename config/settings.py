import os
import sys  # 🎯 AGGIUNTO: Fondamentale per rilevare la compressione PyInstaller
from pathlib import Path

# =========================================================================
# 🛡️ DETERMINAZIONE DINAMICA DELLA RADICE (SCRIPT vs ESEGUIBILE .EXE)
# =========================================================================
# Se l'applicazione è pacchettizzata in un .exe, BASE_DIR diventa la cartella ospite dell'eseguibile.
# Se gira normalmente come script di sviluppo (.py), punta alla cartella radice del progetto.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(ENV_FILE)


class Settings:
    # =========================================================================
    # AUTENTICAZIONE ED ENTI ESTERNI
    # =========================================================================
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # =========================================================================
    # PORTALE SISTER (URL DI RIFERIMENTO)
    # =========================================================================
    SISTER_URL: str = "https://iampe.agenziaentrate.gov.it/sam/UI/Login?realm=/agenziaentrate"
    POST_LOGIN_URL: str = "https://sister3.agenziaentrate.gov.it/Visure/SceltaServizio.do?tipo=/T/TM/VCVC_"
    SISTER_NCT_PATH: str = POST_LOGIN_URL
    SISTER_NCF_PATH: str = POST_LOGIN_URL

    # =========================================================================
    # PERCORSI DI SISTEMA (PATHS LOCALI AUTO-ADATTIVI)
    # =========================================================================
    DATA_DIR: Path = BASE_DIR / "data"
    INPUT_DIR: Path = DATA_DIR / "input"
    INPUT_EXCEL: Path = INPUT_DIR / "piano particellare.xlsx"
    CACHE_DIR: Path = DATA_DIR / "cache"
    OUTPUT_DIR: Path = DATA_DIR / "output_tree"
    ISTAT_CSV: Path = Path("utils/Elenco-comuni-italiani.csv")
    STATE_FILE: Path = BASE_DIR / "scraper" / "state" / "state.json"
    # Re-routing dinamico dei log nella cartella roaming utente (Windows: %APPDATA%)
    # Evita problemi di permessi quando l'applicazione è pacchettizzata in un .exe
    _appdata = os.getenv("APPDATA")
    if _appdata:
        LOG_FILE: Path = Path(_appdata) / "StramBot" / "logs" / "orchestrator.log"
    else:
        LOG_FILE: Path = BASE_DIR / "logs" / "sister.log"
    EXCEPTIONS_FILE: Path = OUTPUT_DIR / "eccezioni_report.xlsx"

    # =========================================================================
    # AUTOMAZIONE PLAYWRIGHT (TIMEOUT E TEMPISTICA)
    # =========================================================================
    HEADLESS: bool = False
    TIMEOUT_MS: int = 30_000
    DOWNLOAD_TIMEOUT_MS: int = 60_000

    # Forchetta di tempo randomica (Effetto Jitter Umano)
    MIN_REQUEST_PAUSE_S: float = 1.5
    MAX_REQUEST_PAUSE_S: float = 8.9

    MIN_RETRIES: int = 1
    MAX_RETRIES: int = 3

    # =========================================================================
    # LOGICA DI BUSINESS (CATEGORIE TRASVERSALI)
    # =========================================================================
    CATEGORY_BLOCKS: tuple[str, ...] = (
        "cabine",
        "invarianza idraulica",
        "opere accessorie idraulica",
        "cancelli",
        "stradelle esterne",
        "stradelle esistenti",
    )

    # =========================================================================
    # SELETTORI RADICE (FORM IMMOBILI SISTER)
    # =========================================================================
    SEL_CATASTO_DROPDOWN: str = "select[name='tipoCatasto']"
    SEL_FORM_RICHIEDENTE: str = "input[name='richiedente']"
    SEL_FORM_MOTIVAZIONE: str = "input[name='motivoText']"

    # --- Selettori NCT (Terreni) ---
    SEL_NCT_PROVINCIA: str = "select[name='listacom']"
    SEL_NCT_COMUNE: str = "select[name='denomComune']"
    SEL_NCT_FOGLIO: str = "input[name='foglio']"
    SEL_NCT_PARTICELLA: str = "input[name='particella1']"
    SEL_NCT_SUBMIT: str = "input[type='submit'][name='scelta'][value='Visura']"

    # --- Selettori NCF (Fabbricati) ---
    SEL_NCF_PROVINCIA: str = "select[name='listacom']"
    SEL_NCF_COMUNE: str = "select[name='denomComune']"
    SEL_NCF_FOGLIO: str = "input[name='foglio']"
    SEL_NCF_PARTICELLA: str = "input[name='particella1']"
    SEL_NCF_SUB: str = "input[name='subalterno1']"
    SEL_NCF_SUBMIT: str = "input[type='submit'][name='scelta'][value='Visura']"

    # =========================================================================
    # SELETTORI VALIDAZIONE E SCARICAMENTO (SCHERMATA CAPTCHA)
    # =========================================================================
    SEL_CAPTCHA_INPUT: str = "input[name='inCaptchaChars']"
    SEL_DOWNLOAD_PDF: str = "input[type='submit'][name='metodo'][value='Salva']"
    SEL_BUTTON_INDIETRO: str = "input[type='submit'][value='Indietro']"

    CAPTCHA_TIMEOUT_S: int = 25

    # Pausa di respiro subito dopo aver cliccato "Visura"
    POST_CLICK_PAUSE_S: float = 5.5

    # --- Selettori Area Richieste Differite (Recupero KO) ---
    SEL_LINK_RICHIESTE: str = "a[href*='ConsultazioneRichieste.do?metodo=lista']"
    SEL_ROW_RICHIESTA: str = "tr:has(a[href*='metodo=salva'])"