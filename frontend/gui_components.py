import customtkinter as ctk

class ControlPanel(ctk.CTkFrame):
    def __init__(self, master, provinces: list[str], default_excel: str, api_key: str, **kwargs):
        super().__init__(master, **kwargs)

        self.input_path_var = ctk.StringVar(value=default_excel)
        self.province_var = ctk.StringVar(value=provinces[0] if provinces else "")
        self.api_key_var = ctk.StringVar(value=api_key or "")

        self.title_label = ctk.CTkLabel(self, text="Pannello di Controllo", font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.grid(row=0, column=0, columnspan=2, pady=(10, 20), sticky="w")

        self.excel_label = ctk.CTkLabel(self, text="File Excel di input")
        self.excel_label.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 5))
        self.excel_entry = ctk.CTkEntry(self, textvariable=self.input_path_var, width=380)
        self.excel_entry.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.browse_button = ctk.CTkButton(self, text="Sfoglia File", width=150)
        self.browse_button.grid(row=3, column=0, padx=10, pady=(0, 20), sticky="w")

        self.province_label = ctk.CTkLabel(self, text="Provincia ufficio di riferimento")
        self.province_label.grid(row=4, column=0, sticky="w", padx=10, pady=(0, 5))
        self.province_dropdown = ctk.CTkOptionMenu(self, values=provinces, variable=self.province_var, width=280)
        self.province_dropdown.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 20), sticky="w")

        self.api_label = ctk.CTkLabel(self, text="OpenAI API Key")
        self.api_label.grid(row=6, column=0, sticky="w", padx=10, pady=(0, 5))
        self.api_entry = ctk.CTkEntry(self, textvariable=self.api_key_var, show="*", width=380)
        self.api_entry.grid(row=7, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.save_api_button = ctk.CTkButton(self, text="Salva API Key", width=150)
        self.save_api_button.grid(row=8, column=0, padx=10, pady=(0, 20), sticky="w")

        self.clear_cache_button = ctk.CTkButton(self, text="Svuota Cache", fg_color="#AA2222", hover_color="#CC3333")
        self.clear_cache_button.grid(row=9, column=0, padx=10, pady=(0, 20), sticky="w")

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def set_input_path(self, path: str) -> None:
        self.input_path_var.set(path)

    def get_selected_province(self) -> str:
        return self.province_var.get().strip()

    def get_api_key(self) -> str:
        return self.api_key_var.get().strip()

    def set_api_key(self, api_key: str) -> None:
        self.api_key_var.set(api_key)


class BridgePanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.title_label = ctk.CTkLabel(self, text="Ponte di Sblocco", font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.pack(pady=(10, 20), anchor="w")

        self.start_button = ctk.CTkButton(self, text="AVVIA AUTOMAZIONE", width=240, height=60, fg_color="#0a84ff")
        self.start_button.pack(pady=(0, 20))

        self.alert_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color="#ff5f57")
        self.alert_label.pack(pady=(0, 20), padx=10, fill="x")

        self.unblock_button = ctk.CTkButton(self, text="SBLOCCA AUTOMAZIONE", width=220, fg_color="#f5a623")
        self.unblock_button.pack(pady=(0, 10))

        self.stop_button = ctk.CTkButton(self, text="STOP E CHIUDI", width=220, fg_color="#cc3f3f", hover_color="#ff5f5f")
        self.stop_button.pack(pady=(0, 10))

        self.info_label = ctk.CTkLabel(
            self,
            text="Quando l'automazione si ferma, premi SBLOCCA AUTOMAZIONE. Usa STOP E CHIUDI per arrestare con controllo.",
            wraplength=320,
            justify="left",
        )
        self.info_label.pack(pady=(10, 0), padx=10, fill="x")

        self._blinking = False
        self._blink_state = False

    def set_paused(self, message: str) -> None:
        self.alert_label.configure(text=message, text_color="#ffcc00")
        self._start_blinking()

    def set_resumed(self, message: str = "Automazione ripristinata.") -> None:
        self.alert_label.configure(text=message, text_color="#80ff80")
        self._stop_blinking()

    def _start_blinking(self) -> None:
        self._blinking = True
        self._blink()

    def _stop_blinking(self) -> None:
        self._blinking = False
        self.alert_label.configure(fg_color="transparent")

    def _blink(self) -> None:
        if not self._blinking:
            return
        self._blink_state = not self._blink_state
        self.alert_label.configure(text_color="#ffcc00" if self._blink_state else "#ff5f57")
        self.after(600, self._blink)


class StatusPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.title_label = ctk.CTkLabel(self, text="Monitoraggio in Tempo Reale", font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.pack(pady=(10, 20), anchor="w")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=10, pady=(0, 15))

        self.counter_frame = ctk.CTkFrame(self)
        self.counter_frame.pack(fill="x", padx=10, pady=(0, 15))
        self.counter_frame.grid_columnconfigure((0, 1), weight=1)

        self.processed_label = ctk.CTkLabel(self.counter_frame, text="Elaborati: 0 / 0")
        self.processed_label.grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.downloaded_label = ctk.CTkLabel(self.counter_frame, text="Scaricati: 0")
        self.downloaded_label.grid(row=0, column=1, sticky="w", padx=8, pady=4)
        self.cached_label = ctk.CTkLabel(self.counter_frame, text="Saltati (cache): 0")
        self.cached_label.grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.errors_label = ctk.CTkLabel(self.counter_frame, text="Errori: 0")
        self.errors_label.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        self.log_box = ctk.CTkTextbox(self, width=520, height=420, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_progress(self, processed: int, total: int, downloaded: int, cached: int, errors: int) -> None:
        self.processed_label.configure(text=f"Elaborati: {processed} / {total}")
        self.downloaded_label.configure(text=f"Scaricati: {downloaded}")
        self.cached_label.configure(text=f"Saltati (cache): {cached}")
        self.errors_label.configure(text=f"Errori: {errors}")
        if total:
            self.progress.set(min(processed / total, 1.0))
        else:
            self.progress.set(0)
