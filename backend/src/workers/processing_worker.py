from __future__ import annotations

import threading
import uuid
from typing import Callable

from ..pipeline import ProcessingPipeline
from ..review import ReviewStore


class ProcessingWorker:
    """Runs a ProcessingPipeline job on a background thread.

    This replaces the old PyQt `QThread` + `pyqtSignal` worker: there is no
    GUI event loop to deliver signals into anymore, so progress/completion/
    failure are instead reported through plain callbacks, and current state
    is polled via `.status()` — which is what the FastAPI job endpoints use.
    """

    def __init__(self, video_path: str, config=None, source_name: str | None = None,
                 review_store: ReviewStore | None = None,
                 on_progress: Callable[[int, int, int, int], None] | None = None,
                 on_completed: Callable[[object], None] | None = None,
                 on_failed: Callable[[str], None] | None = None):
        self.job_id = uuid.uuid4().hex[:12]
        self.video_path = video_path
        self.config = config
        self.source_name = source_name
        self.review_store = review_store
        self.on_progress = on_progress
        self.on_completed = on_completed
        self.on_failed = on_failed

        self.pipeline: ProcessingPipeline | None = None
        self._thread: threading.Thread | None = None
        self.state = "idle"          # idle | processing | completed | failed | cancelled
        self.result = None
        self.error: str | None = None
        self.progress = {"current": 0, "total": 0, "detected": 0, "redactions": 0}

    def start(self) -> "ProcessingWorker":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.state = "processing"
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self.pipeline = ProcessingPipeline(self.config, self.review_store)
            result = self.pipeline.process(
                self.video_path, self.source_name, self._handle_progress,
            )
            if result.cancelled:
                self.state = "cancelled"
            else:
                self.state = "completed"
                self.result = result
                if self.on_completed:
                    self.on_completed(result)
        except Exception as exc:
            self.state = "failed"
            self.error = str(exc)
            if self.on_failed:
                self.on_failed(str(exc))

    def _handle_progress(self, current: int, total: int, detected: int, redactions: int) -> None:
        self.progress = {"current": current, "total": total, "detected": detected, "redactions": redactions}
        if self.on_progress:
            self.on_progress(current, total, detected, redactions)

    def cancel(self) -> None:
        if self.pipeline:
            self.pipeline.cancel()

    def status(self) -> dict:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "progress": self.progress,
            "error": self.error,
        }
