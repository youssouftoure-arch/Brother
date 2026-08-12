# main.py — Entrypoint principale dell'automazione catastale
import multiprocessing
import os
import subprocess
import sys

# 🚨 STABILIZZATORE ROTTA PLAYWRIGHT: DA METTERE COME PRIMISSIMA COSA IN CIMA AL FILE
# Forza Playwright a usare una cartella permanente sul PC anziché la directory temporanea volatile _MEIxxxx
if os.name == 'nt': # Se siamo su Windows
    local_appdata = os.getenv("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(local_appdata, "ms-playwright")

def _ensure_playwright_browsers():
    """
    Controlla e installa i binari di Chromium in modo totalmente isolato.
    Garantisce l'immunità totale da Fork-Bomb negli eseguibili PyInstaller.
    """
    # 1. Controlliamo se siamo dentro l'EXE congelato
    is_frozen = bool(getattr(sys, '_MEIPASS', None))
    
    if is_frozen:
        # 🚨 SICUREZZA ASSOLUTA: Dentro l'EXE non usiamo MAI sys.executable
        meipass = getattr(sys, '_MEIPASS', '')
        driver_cmd = os.path.normpath(os.path.join(meipass, "playwright", "driver", "playwright.cmd"))
        
        # Eseguiamo il setup SOLO se il driver interno esiste fisicamente
        if os.path.exists(driver_cmd):
            try:
                # 'creationflags' evita il flash fastidioso di finestre nere prompt a schermo
                subprocess.run(
                    [driver_cmd, "install", "chromium"], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000  # CREATE_NO_WINDOW per Windows
                )
            except Exception:
                pass
    else:
        # 🔵 AMBIENTE LOCALE (Sviluppo su VS Code / venv)
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


def inizializza_playwright_blindato():
    """Nome storico mantenuto per la GUI e per gli eseguibili già configurati."""
    return _ensure_playwright_browsers()


def main():
    from frontend import run_app

    inizializza_playwright_blindato()
    run_app()


if __name__ == "__main__":
    inizializza_playwright_blindato()
    multiprocessing.freeze_support()
    main()
