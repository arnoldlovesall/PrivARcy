"""Qt-thread adapter around the framework-agnostic ProcessingPipeline.

backend/src stays free of any GUI dependency (so it can also run headless,
e.g. behind the FastAPI app in backend/app). This is the one place where
that pipeline gets wrapped in a QThread so PyQt signals can drive the
Process page's progress bar / completion / error states.
"""
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from PyQt5.QtCore import QThread, pyqtSignal

from src.pipeline import ProcessingPipeline


class QtProcessingWorker(QThread):
    progress = pyqtSignal(int, int, int, int)   # current, total, detected, redactions
    completed = pyqtSignal(object)               # ProcessingResult
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, video_path, config=None, source_name=None, review_store=None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.config = config
        self.source_name = source_name
        self.review_store = review_store
        self.pipeline = None

    def run(self):
        try:
            self.pipeline = ProcessingPipeline(self.config, self.review_store)
            result = self.pipeline.process(self.video_path, self.source_name, self.progress.emit)
            if result.cancelled:
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self):
        if self.pipeline:
            self.pipeline.cancel()
