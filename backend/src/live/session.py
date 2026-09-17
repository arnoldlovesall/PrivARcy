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
from ..tracker.simple import _iou
from ..utils.logging import get_logger
from ..video import VideoWriter

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

        self.detector = YoloDetector(self.config.model_path, self.config.low_threshold, self.config.device)
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
        self._writer = None
        self.output_path: str | None = None

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
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = str(self.config.output_dir / f"live_{stamp}_redacted.mp4")
        self._writer = None

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._capture_thread.start()
        self._detection_thread.start()
        return True

    def stop(self) -> dict:
        self._running = False
        for thread in (self._capture_thread, self._detection_thread):
            if thread:
                thread.join(timeout=2)
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        return {
            "output_path": self.output_path,
            "frames": self.stats.get("frames", 0),
            "redacted": self.stats.get("redacted", 0),
            "flagged": self.stats.get("flagged", 0),
        }

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

            if self._writer is None and self.output_path:
                height, width = display_frame.shape[:2]
                fps = (self.actual_resolution[2] if self.actual_resolution else 0) or 30
                try:
                    self._writer = VideoWriter(self.output_path, fps, (width, height))
                except ValueError as exc:
                    log.warning("Live session could not open output writer: %s", exc)
                    self._writer = False
            if self._writer:
                self._writer.write(display_frame)

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
            interval = max(1, self.config.detection_interval)
            if interval > 1 and self._detection_pass % interval != 1:
                time.sleep(0.01)
                continue

            detected = self.tracker.update(
                self.detector.detect(frame, scale=self.config.detection_scale)
            )
            detected = [d for d in detected if self._class_enabled(d.label)]

            known_faces = []
            if any(category_for_label(d.label) == "FACE" for d in detected):
                try:
                    known_faces = self.registry.recognize_frame(frame)
                except Exception as exc:
                    log.debug("Live face recognition skipped: %s", exc)

            regions = []
            for d in detected:
                category = category_for_label(d.label)
                text_sensitive, ocr_text, classification_label, classification_conf = self._text_sensitive_for(
                    d, frame, category
                )
                known_consent = False
                if category == "FACE" and known_faces:
                    known_consent = any(
                        match["match"].matched and _iou(d.bbox, match["bbox"]) > 0.3
                        for match in known_faces
                    )

                action = self.decision.decide(d.confidence, known_consent, text_sensitive)
                if action == "redact":
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
                            ocr_text=ocr_text, classification=classification_label,
                            classification_confidence=classification_conf,
                        )

            with self._regions_lock:
                self._current_regions = regions
            self.stats["chunks"] += 1
            self.smoother.forget_stale({getattr(d, "track_id", None) for d in detected})

    def _text_sensitive_for(self, detection, frame, category: str) -> tuple[bool, str | None, str | None, float | None]:
        """OCR + classify a text-bearing detection, using a per-track cache."""
        if category not in {"ID", "DOCUMENT", "CREDENTIAL", "LICENSE_PLATE"}:
            return False, None, None, None

        track_id = getattr(detection, "track_id", None)
        cached = self._ocr_cache.get(track_id) if track_id is not None else None
        if cached is not None and self._detection_pass - cached["last_pass"] < self.config.ocr_cache_passes:
            return cached["text_sensitive"], cached.get("ocr_text"), cached.get("classification"), cached.get("confidence")

        x1, y1, x2, y2 = detection.bbox
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        text_sensitive = False
        ocr_text = classification = None
        classification_conf = None
        if crop.size:
            ocr_results = self.ocr.extract(crop)
            if ocr_results:
                best = max(ocr_results, key=lambda r: r.confidence)
                ocr_text = best.text
                text_class = self.classifier.classify(ocr_text)
                text_sensitive = text_class.sensitivity == "sensitive"
                classification = text_class.category
                classification_conf = text_class.confidence
                hint = self.classifier.category_hint(text_class)
                if hint:
                    pass  # category re-bucket happens in the file pipeline; live keeps YOLO label

        if track_id is not None:
            self._ocr_cache[track_id] = {
                "text_sensitive": text_sensitive,
                "last_pass": self._detection_pass,
                "ocr_text": ocr_text,
                "classification": classification,
                "confidence": classification_conf,
            }
        return text_sensitive, ocr_text, classification, classification_conf

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
