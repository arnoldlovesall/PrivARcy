from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable

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
from ..video import VideoReader, VideoWriter
from ..utils.logging import get_logger

# Detection categories whose crops are worth running TrOCR on. Faces carry
# no readable text, so they're skipped to save inference time.
TEXT_BEARING_CATEGORIES = {"ID", "DOCUMENT", "CREDENTIAL", "LICENSE_PLATE"}


def _iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


@dataclass
class ProcessingResult:
    output_path: str
    frames: int
    detections: list[dict] = field(default_factory=list)
    redactions: int = 0
    cancelled: bool = False
    source_path: str = ""


class ProcessingPipeline:
    """Custom-trained YOLO26 detection -> TrOCR extraction -> rule-based
    sensitivity classification -> confidence-gated decision -> redaction.

    Uncertain detections (T_low <= confidence < T_high, or ambiguous text
    sensitivity) are written into the shared ReviewStore for human review
    instead of being silently auto-redacted or discarded.
    """

    def __init__(self, config: AppConfig | None = None, review_store: ReviewStore | None = None):
        self.config = config or AppConfig()
        self.config.ensure_directories()
        # Filter at T_low so [T_low, T_high) can reach the review queue.
        # T_high is applied later by PrivacyDecisionEngine, not by YOLO.
        self.detector = YoloDetector(self.config.model_path, self.config.low_threshold, self.config.device)
        self.ocr = OCRService(self.config.ocr_model_path, device=None if self.config.device == "auto" else self.config.device)
        self.classifier = PrivacyTextClassifier(self.config.classifier_weights_path)
        self.registry = FaceRegistry(self.config.registry_dir)
        self.decision = PrivacyDecisionEngine(self.config.confidence_threshold, self.config.low_threshold)
        self.tracker = IoUTracker(self.config.iou_threshold, self.config.track_termination)
        self.redactor = RedactionEngine(self.config.redaction_method, self.config.blur_strength)
        self.smoother = TemporalSmoother(self.config.temporal_smoothing)
        self.review_store = review_store
        self.cancelled = False
        self.log = get_logger(__name__)

    def cancel(self) -> None:
        self.cancelled = True

    def _class_enabled(self, label: str) -> bool:
        needle = label.strip().lower()
        return any(needle in cls or cls in needle for cls in self.config.enabled_classes)

    def _crop(self, frame, bbox):
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def process(self, video_path: str, source_name: str | None = None,
                progress: Callable[[int, int, int, int], None] | None = None,
                frame_callback=None) -> ProcessingResult:
        reader = VideoReader(video_path)
        source_name = source_name or Path(video_path).name
        output = self.config.output_dir / f"{Path(video_path).stem}_redacted.mp4"
        writer = None
        events: list[dict] = []
        redactions = 0
        index = 0
        last_regions: list[tuple[int, int, int, int]] = []
        interval = max(1, self.config.detection_interval)
        start = perf_counter()
        try:
            for index, frame in enumerate(reader, 1):
                if self.cancelled:
                    break
                if writer is None:
                    writer = VideoWriter(output, reader.fps, (frame.shape[1], frame.shape[0]))

                skip_detect = interval > 1 and (index - 1) % interval != 0
                if skip_detect:
                    frame = self.redactor.apply(frame, last_regions)
                    writer.write(frame)
                    if frame_callback:
                        frame_callback(frame)
                    if progress:
                        progress(index, reader.total_frames, len(events), redactions)
                    continue

                detected = self.tracker.update(self.detector.detect(frame, scale=self.config.detection_scale))
                detected = [d for d in detected if self._class_enabled(d.label)]

                known_faces = []
                if any(category_for_label(d.label) == "FACE" for d in detected):
                    try:
                        known_faces = self.registry.recognize_frame(frame)
                    except Exception as exc:
                        self.log.debug("Face recognition skipped: %s", exc)

                regions = []
                for d in detected:
                    category = category_for_label(d.label)
                    known_consent = False
                    if category == "FACE" and known_faces:
                        known_consent = any(
                            match["match"].matched and _iou(d.bbox, match["bbox"]) > 0.3
                            for match in known_faces
                        )

                    ocr_text, text_sensitive = None, False
                    classification_label, classification_conf = None, None
                    if category in TEXT_BEARING_CATEGORIES:
                        crop = self._crop(frame, d.bbox)
                        if crop is not None:
                            ocr_results = self.ocr.extract(crop)
                            if ocr_results:
                                best = max(ocr_results, key=lambda r: r.confidence)
                                ocr_text = best.text
                                text_class = self.classifier.classify(ocr_text)
                                text_sensitive = text_class.sensitivity == "sensitive"
                                classification_label = text_class.category
                                classification_conf = text_class.confidence
                                hint = self.classifier.category_hint(text_class)
                                if hint:
                                    category = hint

                    action = self.decision.decide(d.confidence, known_consent, text_sensitive)
                    status = "confirmed" if action == "redact" else "pending"

                    # Saved so a human-confirmed review item has a real
                    # image on disk for ActiveLearningStore to add to the
                    # training set later — a detection only reaches review
                    # when the model was uncertain about it, which is
                    # exactly the case a retrained model most needs
                    # labeled examples of. Only written for items that
                    # actually reach review (not every detection), to
                    # avoid flooding disk with images no one will use.
                    saved_image_path = None
                    review_item = None
                    if action == "review":
                        saved_image_path = str(
                            self.config.review_frames_dir / f"{Path(video_path).stem}_f{index}.jpg"
                        )
                        cv2.imwrite(saved_image_path, frame)

                    event = {
                        "id": f"det-{index}-{getattr(d, 'track_id', 0)}",
                        "label": d.label.title(),
                        "category": category,
                        "source": source_name,
                        "confidence": d.confidence,
                        "bbox": d.bbox,
                        "frame": index,
                        "track_id": getattr(d, "track_id", None),
                        # MM:SS.ff — matches Review.py's TimelineWidget parser
                        # (`_time_to_seconds`), which reads exactly two parts.
                        "time": f"{int(index / reader.fps) // 60:02d}:{(index / reader.fps) % 60:05.2f}",
                        "status": status,
                        "action": action,
                        "image_path": saved_image_path,
                        "ocr_text": ocr_text,
                        "classification": classification_label,
                        "classification_confidence": classification_conf,
                    }

                    if action == "redact":
                        regions.append(self.smoother.smooth(getattr(d, "track_id", None), d.bbox))
                        redactions += 1
                    elif action == "review" and self.review_store is not None:
                        review_item = self.review_store.add(
                            label=d.label.title(), category=category, source=source_name,
                            frame=index,
                            time=event["time"],
                            confidence=d.confidence,
                            bbox=d.bbox, image_path=saved_image_path, ocr_text=ocr_text,
                            classification=classification_label,
                            classification_confidence=classification_conf,
                        )
                        event["id"] = review_item.id

                    events.append(event)

                self.smoother.forget_stale({getattr(d, "track_id", None) for d in detected})
                last_regions = regions
                frame = self.redactor.apply(frame, regions)
                writer.write(frame)
                if frame_callback:
                    frame_callback(frame)
                if progress:
                    progress(index, reader.total_frames, len(events), redactions)

            self.log.info("Processing finished in %.1fs", perf_counter() - start)
            return ProcessingResult(
                str(output), index, events, redactions, self.cancelled, source_path=str(video_path),
            )
        finally:
            reader.close()
            if writer:
                writer.close()
