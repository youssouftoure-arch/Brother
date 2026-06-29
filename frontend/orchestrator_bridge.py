import logging
import threading
from queue import Queue
from typing import Optional

from core.orchestrator import MasterOrchestrator

logger = logging.getLogger("Frontend")

class OrchestratorRunner:
    def __init__(self, status_queue: Queue, control_event: threading.Event, stop_event: threading.Event):
        self.status_queue = status_queue
        self.control_event = control_event
        self.stop_event = stop_event
        self.thread: Optional[threading.Thread] = None
        self.exception: Optional[Exception] = None
        self.running = False

    def start(self, input_excel: str, office_province: str | None) -> None:
        if self.thread and self.thread.is_alive():
            return

        self.exception = None
        self.running = True
        self.control_event.set()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            args=(input_excel, office_province),
            daemon=True,
        )
        self.thread.start()
        self.status_queue.put({"type": "run_started", "message": "Automazione avviata."})

    def _run(self, input_excel: str, office_province: str | None) -> None:
        try:
            orchestrator = MasterOrchestrator(
                control_event=self.control_event,
                status_queue=self.status_queue,
                stop_event=self.stop_event,
                office_province=office_province,
                input_excel=input_excel,
            )
            orchestrator.run()
        except Exception as exc:
            self.exception = exc
            logger.exception("Orchestratore terminato con un errore.")
        finally:
            self.running = False
            self.status_queue.put({
                "type": "run_finished",
                "exception": str(self.exception) if self.exception else None,
            })

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def request_stop(self) -> None:
        self.stop_event.set()
        try:
            self.status_queue.put({
                "type": "stop_requested",
                "message": "Richiesta stop ricevuta. Verrà completata la fase finale...",
            })
        except Exception:
            pass

    def request_resume(self) -> None:
        self.control_event.set()
