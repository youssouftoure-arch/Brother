# scraper/browser_manager.py — Gestione del ciclo di vita del browser con blocco anti-crash ed evasioni anti-bot
from playwright.sync_api import sync_playwright, BrowserContext, Page
from config.settings import Settings

class BrowserManager:
    def __init__(self):
        self._pw = None
        self._browser = None
        self.context: BrowserContext = None
        self.current_page: Page = None

    def __enter__(self) -> "BrowserManager":
        if not Settings.STATE_FILE.exists():
            raise FileNotFoundError(
                f"state.json non trovato in {Settings.STATE_FILE}. "
                "Esegui prima il login manuale tramite l'interfaccia di sblocco."
            )
        self._pw = sync_playwright().start()

        # 🎯 SCUDO STEALTH 1: Lancio di Chromium con flag di mascheramento nativi
        # Elimina i blocchi di automazione visibili a livello di processo
        self._browser = self._pw.chromium.launch(
            headless=Settings.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",  # Disattiva le impronte digitali da robot
                "--disable-infobars",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--window-position=0,0",
            ]
        )
        
        # Caricamento del contesto con lo stato di autenticazione (cookie e sessione del login)
        # Iniettiamo anche un User-Agent umano identico a un Chrome stabile su Windows
        self.context = self._browser.new_context(
            storage_state=str(Settings.STATE_FILE),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1366, "height": 768},
        )

        # Iniezione globale di script per mascherare proprietà sensibili prima del caricamento
        try:
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['it-IT', 'it', 'en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.navigator.chrome = { runtime: {}, loadTimes: Date.now };
            """)
        except Exception:
            pass
        return self

    def new_page(self) -> Page:
        page = self.context.new_page()
        self.current_page = page
        return page

    def _is_browser_reachable(self) -> bool:
        if not self._browser or not self.context:
            return False

        try:
            if hasattr(self._browser, "is_connected") and not self._browser.is_connected():
                return False
        except Exception:
            return False

        if self.current_page:
            try:
                if not self.current_page.is_closed():
                    return True
            except Exception:
                pass

        try:
            for page in self.context.pages:
                try:
                    if not page.is_closed():
                        return True
                except Exception:
                    continue
        except Exception:
            return False

        return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Metodo di uscita dal blocco 'with'. 
        Se intercetta un crash (exc_type non è None), congela il browser per il logout manuale.
        """
        # =========================================================================
        # 🔐 PROTEZIONE ANTI-LOCKOUT IN CASO DI CRASH
        # =========================================================================
        if exc_type is not None:
            if self._is_browser_reachable():
                print("\n" + "X" * 70)
                print("🚨 ATTENZIONE: IL PROGRAMMA HA RILEVATO UN CRASH CRITICO!")
                print("👉 La finestra del browser è stata congelata volutamente in primo piano.")
                print("👉 Fai clic sul tasto 'ESCI' o 'LOGOUT' dentro Sister per liberare lo slot sul server.")
                print("X" * 70 + "\n")
                input(">>> Quando hai completato il LOGOUT manuale su Sister, premi INVIO qui per chiudere... <<<")
                print("\nChiusura dei motori di automazione in corso...")
            else:
                print("\n" + "X" * 70)
                print("🚨 ATTENZIONE: Il browser non è più raggiungibile o si è chiuso autonomamente.")
                print("👉 Skip del logout manuale e proseguo direttamente con la fase finale.")
                print("X" * 70 + "\n")
        # =========================================================================

        # Dismissione standard delle risorse Playwright
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass