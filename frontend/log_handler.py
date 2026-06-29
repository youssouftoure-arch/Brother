import logging

class TkinterLogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        try:
            message = self.format(record)
            if self.text_widget is None:
                return
            self.text_widget.after(0, self._append, message)
        except Exception:
            self.handleError(record)

    def _append(self, message):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", message + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")
