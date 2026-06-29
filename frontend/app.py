import logging
import os
import queue
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    from PIL import Image, ImageTk  # 🎯 AGGIUNTO: ImageTk è fondamentale per l'icona del frame
except ImportError:
    Image = None
    ImageTk = None

from config.settings import BASE_DIR, Settings, ENV_FILE
from utils.istat_lookup import GetProvince
from .gui_components import BridgePanel, ControlPanel, StatusPanel
from .log_handler import TkinterLogHandler
from .orchestrator_bridge import OrchestratorRunner


class SisterAutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Brother Automation")
        self.geometry("1360x820")
        self.minsize(1240, 760)

        # 🎯 SCUDO WINDOWS: Forza il sistema operativo a slegare l'app da python.exe
        # Questo sblocca la visualizzazione del logo nella barra delle applicazioni in basso
        if os.name == "nt":
            import ctypes
            try:
                myappid = "brotherautomation.sisterextractor.v1.0"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.status_queue: queue.Queue[dict] = queue.Queue()
        self.control_event = threading.Event()
        self.control_event.set()
        self.stop_event = threading.Event()
        self.stop_event.clear()
        self.runner = OrchestratorRunner(self.status_queue, self.control_event, self.stop_event)

        self.provinces = self._load_provinces()

        # 🎯 CONFIGURAZIONE GRIGLIA PANORAMICA (2 Colonne, 3 Righe bilanciate)
        self.columnconfigure((0, 1), weight=1, uniform="column")
        self.rowconfigure(1, weight=1)  # Riga logs
        self.rowconfigure(2, weight=8)  #riga pannelli operativi

        # Header con logo e titolo applicazione (Esteso su entrambe le colonne)
        self.header_frame = ctk.CTkFrame(self, fg_color="#15171f", corner_radius=20)
        

        # =========================================================================
        # 👑 GESTIONE LOGO UNIVERSALE (FRAME + TASKBAR)
        # =========================================================================
        app_icon_path = BASE_DIR / "frontend" / "assets" / "logohq.ico"
        logo_png_path = BASE_DIR / "frontend" / "assets" / "logohq.png"

        # Passo A: Aggancio dell'icona bitmap tradizionale (per la barra del titolo Windows)
        if app_icon_path.exists():
            try:
                self.iconbitmap(str(app_icon_path))
            except Exception:
                pass

        # Passo B: Aggancio fotografico tramite PNG (Sigilla l'icona su Windows/Linux/Mac)
        if logo_png_path.exists() and Image is not None and ImageTk is not None:
            try:
                img = Image.open(logo_png_path)
                photo = ImageTk.PhotoImage(img)
                self.wm_iconphoto(False, photo)
                
                # 🛡️ CRITICO: Salviamo il riferimento in un attributo d'istanza. 
                self._app_icon_photo_ref = photo 
            except Exception:
                pass

        # Rendering del logo PNG dentro l'header dell'applicazione
        if Image is not None and logo_png_path.exists():
            try:
                logo_image = ctk.CTkImage(light_image=Image.open(logo_png_path), size=(36, 36))
                logo_label = ctk.CTkLabel(self.header_frame, image=logo_image, text="")
                logo_label.image = logo_image
                logo_label.grid(row=0, column=0, padx=(10, 10), pady=15, sticky="w")
            except Exception:
                pass
        # =========================================================================

        header_title = ctk.CTkLabel(self.header_frame, text="Brother Automation", font=ctk.CTkFont(size=24, weight="bold"))
        header_title.grid(row=0, column=1, padx=(0, 10), pady=15, sticky="w")

        # 🟢 PANNELLO 1: Impostazioni e Controllo (In alto a sinistra)
        self.control_panel = ControlPanel(
            self,
            provinces=self.provinces,
            default_excel=str(Settings.INPUT_EXCEL),
            api_key=Settings.OPENAI_API_KEY,
            fg_color="#1f1f2a",
            corner_radius=20,
        )
        self.control_panel.grid(row=1, column=0, padx=15, pady=15, sticky="nsew")

        # 🔵 PANNELLO 2: Ponte di sblocco Sister (In alto a destra)
        self.bridge_panel = BridgePanel(
            self,
            fg_color="#1f1f2a",
            corner_radius=20,
        )
        self.bridge_panel.grid(row=1, column=1, padx=15, pady=15, sticky="nsew")

        # 🟡 PANNELLO 3: Console dei Log e Status (In basso, estesa orizzontalmente)
        self.status_panel = StatusPanel(
            self,
            fg_color="#1f1f2a",
            corner_radius=20,
        )
        self.status_panel.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

        # Configurazione dei comandi dei bottoni
        self.control_panel.browse_button.configure(command=self._browse_excel)
        self.control_panel.save_api_button.configure(command=self._save_api_key)
        self.control_panel.clear_cache_button.configure(command=self._clear_cache)
        self.bridge_panel.start_button.configure(command=self._start_automation)
        self.bridge_panel.unblock_button.configure(command=self._unlock_automation)
        self.bridge_panel.stop_button.configure(command=self._stop_automation)

        self._attach_log_handler()
        self.after(200, self._process_status_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_provinces(self) -> list[str]:
        try:
            raw = GetProvince().df.get("provincia_full", [])
            return sorted({str(item).strip() for item in raw if str(item).strip()})
        except Exception:
            return []

    def _attach_log_handler(self) -> None:
        root_logger = logging.getLogger()
        existing = [h for h in root_logger.handlers if isinstance(h, TkinterLogHandler)]
        if existing:
            return

        handler = TkinterLogHandler(self.status_panel.log_box)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    def _browse_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleziona file Excel",
            filetypes=[("File Excel", "*.xlsx *.xls")],
        )
        if path:
            self.control_panel.set_input_path(path)

    def _save_api_key(self) -> None:
        api_key = self.control_panel.get_api_key().strip()
        if not api_key:
            messagebox.showwarning("Attenzione", "La API key non può essere vuota.")
            return

        try:
            self._write_env_variable("OPENAI_API_KEY", api_key)
            Settings.OPENAI_API_KEY = api_key
            self.control_panel.set_api_key(api_key)
            messagebox.showinfo("Salvataggio completato", "OpenAI API Key salvata correttamente in .env.")
        except Exception as exc:
            messagebox.showerror("Errore", f"Impossibile salvare la API key: {exc}")

    def _write_env_variable(self, key: str, value: str) -> None:
        env_path = ENV_FILE
        env_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        updated = False
        new_lines = []
        for raw in lines:
            if raw.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                updated = True
            else:
                new_lines.append(raw)

        if not updated:
            new_lines.append(f"{key}={value}")

        env_path.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")
        os.environ[key] = value

    def _clear_cache(self) -> None:
        if not Settings.CACHE_DIR.exists() or not Settings.CACHE_DIR.is_dir():
            messagebox.showinfo("Cache", "La cartella cache non esiste o non contiene file.")
            return

        if not messagebox.askyesno(
            "Conferma svuota cache",
            "Sei sicuro di voler eliminare tutti i file nella cache? Queste operazioni non sono reversibili.",
        ):
            return

        removed = 0
        for file_path in Settings.CACHE_DIR.rglob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    removed += 1
                except Exception:
                    pass

        messagebox.showinfo("Cache", f"Cache svuotata. File eliminati: {removed}")

    def _start_automation(self) -> None:
        if self.runner.is_alive():
            messagebox.showwarning("Attenzione", "L'automazione è già in esecuzione.")
            return

        input_excel = self.control_panel.input_path_var.get().strip() or str(Settings.INPUT_EXCEL)
        office_province = self.control_panel.get_selected_province() or None

        self.status_panel.update_progress(0, 0, 0, 0, 0)
        self.bridge_panel.set_resumed("Avvio automazione in corso...")
        self.runner.start(input_excel, office_province)

    def _unlock_automation(self) -> None:
        if not self.runner.is_alive():
            messagebox.showinfo("Info", "Nessuna automazione in pausa al momento.")
            return

        self.control_event.set()
        self.bridge_panel.set_resumed("Segnale di sblocco inviato.")

    def _stop_automation(self) -> None:
        if not self.runner.is_alive():
            messagebox.showinfo("Info", "Nessuna automazione in esecuzione da arrestare.")
            return

        if not messagebox.askyesno(
            "Conferma stop",
            "Vuoi interrompere l'esecuzione e passare alla fase finale di folder building?",
        ):
            return

        self.runner.request_stop()
        self.control_event.set()
        self.bridge_panel.set_paused("Richiesta di stop inviata. Proseguo verso la fase finale...")

    def _process_status_queue(self) -> None:
        while True:
            try:
                status = self.status_queue.get_nowait()
            except queue.Empty:
                break

            if status["type"] == "progress":
                self.status_panel.update_progress(
                    status.get("processed", 0),
                    status.get("total", 0),
                    status.get("downloaded", 0),
                    status.get("cached", 0),
                    status.get("errors", 0),
                )
            elif status["type"] == "paused":
                self.bridge_panel.set_paused(status.get("message", "Operazione richiesta."))
            elif status["type"] == "resumed":
                self.bridge_panel.set_resumed(status.get("message", "Automazione ripartita."))
            elif status["type"] == "run_started":
                self.bridge_panel.set_resumed(status.get("message", "Automazione avviata."))
            elif status["type"] == "stop_requested":
                self.bridge_panel.set_paused(status.get("message", "Stop richiesto."))
            elif status["type"] == "run_finished":
                exception_message = status.get("exception")
                if exception_message:
                    self.bridge_panel.set_paused(f"Automazione terminata con errore: {exception_message}")
                else:
                    self.bridge_panel.set_resumed("Automazione completata correttamente.")

        self.after(200, self._process_status_queue)

    def _on_close(self) -> None:
        if self.runner.is_alive() and not messagebox.askyesno(
            "Chiudi", "L'automazione è in esecuzione. Vuoi uscire comunque?",
        ):
            return
        self.destroy()


def run_app() -> None:
    app = SisterAutomationApp()
    app.mainloop()