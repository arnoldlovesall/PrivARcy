from __future__ import annotations

import sys
import threading
import time
from datetime import datetime

import cv2

from ..classifiers import PrivacyTextClassifier
from ..config import AppConfig, category_for_label
from ..decision import PrivacyDecisionEngine
from ..detectors import YoloDetector
from ..face import FaceRegistry
from ..ocr import OCRService
from ..redaction import RedactionEngine
from ..review import ReviewStore
from ..smoothing import TemporalSmoother
from ..tracker import IoUTracker
from ..utils.logging import get_logger

log = get_logger(__name__)


def discover_cameras(max_devices: int = 12) -> list[dict]:
    """Probe cameras dynamically. DSHOW is a backend preference, never an index."""
    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
    cameras = []
    for index in range(max_devices):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            ok, _ = cap.read()
            cap.release()
            if ok:
                cameras.append({"index": index, "label": f"Camera {index + 1}", "backend": backend})
    return cameras


class LiveSession:
    """Real-time camera privacy pipeline.

    Runs TWO threads instead of one, decoupling camera capture from
    inference — this is the fix for live-stream lag/stutter:

    - `_capture_loop`: reads frames as fast as the camera delivers them,
      redacts each one using whatever regions the detection thread most
      recently computed (cheap — just a blur/mask draw), and publishes it.
      This never blocks on YOLO/TrOCR, so the preview stays smooth even
      while a detection pass is still running.
    - `_detection_loop`: runs independently, as fast as it can keep up —
      grabs the most recent raw frame, runs YOLO26 detection, TrOCR +
      classification (only for *new* tracked objects — see the OCR
      cache), the confidence-gated decision, and publishes the resulting
      regions for the capture loop to use. If it falls behind, it simply
      processes whatever the newest frame is next time, dropping stale
      ones rather than queuing up a backlog.

    Detected regions are therefore up to one detection pass "stale"
    between updates — the standard, accepted tradeoff for real-time video
    redaction (this is how most live-blur camera apps work), and far
    better than the previous single-loop design where every detection
    pass directly stalled frame capture.
    """

    def __init__(self, config: AppConfig | None = None, review_store: ReviewStore | None = None):
        self.config = config or AppConfig()
        self.config.ensure_directories()
        self.review_store = review_store

        self.detector = YoloDetector(self.config.model_path, self.config.confidence_threshold, self.config.device)
        self.ocr = OCRService(self.config.ocr_model_path, device=None if self.config.device == "auto" else self.config.device)
        self.classifier = PrivacyTextClassifier(self.config.classifier_weights_path)
        self.registry = FaceRegistry(self.config.registry_dir)
        self.decision = PrivacyDecisionEngine(self.config.confidence_threshold, self.config.low_threshold)
        self.tracker = IoUTracker(self.config.iou_threshold, self.config.track_termination)
        self.redactor = RedactionEngine(self.config.redaction_method, self.config.blur_strength)
        self.smoother = TemporalSmoother(self.config.temporal_smoothing)

        self._cap = None
        self._capture_thread: threading.Thread | None = None
        self._detection_thread: threading.Thread | None = None
        self._running = False

        self._raw_lock = threading.Lock()
        self._latest_raw_frame = None

        self._regions_lock = threading.Lock()
        self._current_regions: list[tuple[int, int, int, int]] = []

        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None

        # track_id -> {"text_sensitive": bool, "last_pass": int} — see class
        # docstring. Avoids re-running TrOCR on the same held-up ID card /
        # document every single detection pass.
        self._ocr_cache: dict[int, dict] = {}
        self._detection_pass = 0

        self.stats = {"chunks": 0, "frames": 0, "redacted": 0, "flagged": 0}
        self.audit_log: list[dict] = []
        self.started_at: datetime | None = None
        self.camera_index: int | None = None
        self.requested_resolution: tuple[int, int, int] | None = None
        self.actual_resolution: tuple[int, int, int] | None = None

    @property
    def is_live(self) -> bool:
        return self._running

    def _class_enabled(self, label: str) -> bool:
        needle = label.strip().lower()
        return any(needle in cls or cls in needle for cls in self.config.enabled_classes)

    def start(self, camera_index: int, width: int | None = None,
              height: int | None = None, fps: int | None = None) -> bool:
        width = width or self.config.camera_width
        height = height or self.config.camera_height
        fps = fps or self.config.camera_fps

        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(camera_index, backend)
        if not self._cap.isOpened():
            self._cap = None
            return False

        self.requested_resolution = (width, height, fps)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self.actual_resolution = (
            int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or width,
            int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or height,
            int(self._cap.get(cv2.CAP_PROP_FPS)) or fps,
        )

        self._running = True
        self.started_at = datetime.now()
        self.camera_index = camera_index
        self._ocr_cache.clear()
        self._detection_pass = 0

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._capture_thread.start()
        self._detection_thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        for thread in (self._capture_thread, self._detection_thread):
            if thread:
                thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # -- Capture thread: always fast, never blocks on inference ----------
    def _capture_loop(self) -> None:
        while self._running and self._cap is not None:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                log.warning("Live camera dropped mid-stream")
                self._running = False
                break

            self.stats["frames"] += 1
            with self._raw_lock:
                self._latest_raw_frame = frame

            with self._regions_lock:
                regions = list(self._current_regions)
            display_frame = self.redactor.apply(frame, regions) if regions else frame

            ok, buf = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality])
            if ok:
                with self._jpeg_lock:
                    self._latest_jpeg = buf.tobytes()

            time.sleep(0)  # yield to the detection thread

    # -- Detection thread: runs at its own pace, drops stale frames -----
    def _detection_loop(self) -> None:
        while self._running:
            with self._raw_lock:
                frame = self._latest_raw_frame
            if frame is None:
                time.sleep(0.01)
                continue

            self._detection_pass += 1
            detected = self.tracker.update(
                self.detector.detect(frame, scale=self.config.detection_scale)
            )
            detected = [d for d in detected if self._class_enabled(d.label)]

            regions = []
            for d in detected:
                category = category_for_label(d.label)
                text_sensitive = self._text_sensitive_for(d, frame, category)

                action = self.decision.decide(d.confidence, False, text_sensitive)
                if action == "redact":
                    # Smoothed box, not the raw per-frame one — this is
                    # what actually "prevents flickering": the redaction
                    # region is a moving average across this track's
                    # recent detection passes, while the decision above
                    # still used the raw, current box.
                    regions.append(self.smoother.smooth(getattr(d, "track_id", None), d.bbox))
                    self.stats["redacted"] += 1
                    self._add_audit_entry(f"Auto-redacted {d.label.title()}", category)
                elif action == "review":
                    self.stats["flagged"] += 1
                    self._add_audit_entry(f"Flagged {d.label.title()} for review", category)
                    if self.review_store is not None:
                        self.review_store.add(
                            label=d.label.title(), category=category, source="Live Camera",
                            frame=self._detection_pass, time=datetime.now().strftime("%H:%M:%S"),
                            confidence=d.confidence, bbox=d.bbox,
                        )

            with self._regions_lock:
                self._current_regions = regions
            self.stats["chunks"] += 1
            self.smoother.forget_stale({getattr(d, "track_id", None) for d in detected})

    def _text_sensitive_for(self, detection, frame, category: str) -> bool:
        """OCR + classify a text-bearing detection, using a per-track
        cache so a held-up ID card/document doesn't get re-run through
        TrOCR (the most expensive single step here) on every pass."""
        if category not in {"ID", "DOCUMENT", "CREDENTIAL", "LICENSE_PLATE"}:
            return False

        track_id = getattr(detection, "track_id", None)
        cached = self._ocr_cache.get(track_id) if track_id is not None else None
        if cached is not None and self._detection_pass - cached["last_pass"] < self.config.ocr_cache_passes:
            return cached["text_sensitive"]

        x1, y1, x2, y2 = detection.bbox
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        text_sensitive = False
        if crop.size:
            ocr_results = self.ocr.extract(crop)
            if ocr_results:
                text_class = self.classifier.classify(ocr_results[0].text)
                text_sensitive = text_class.sensitivity == "sensitive"

        if track_id is not None:
            self._ocr_cache[track_id] = {"text_sensitive": text_sensitive, "last_pass": self._detection_pass}
        return text_sensitive

    def _add_audit_entry(self, description: str, kind: str) -> None:
        self.audit_log.append({
            "index": len(self.audit_log) + 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "description": description,
            "kind": kind,
        })

    def latest_frame_jpeg(self) -> bytes | None:
        with self._jpeg_lock:
            return self._latest_jpeg

    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return (datetime.now() - self.started_at).total_seconds()
