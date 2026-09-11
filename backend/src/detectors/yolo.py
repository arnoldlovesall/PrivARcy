from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..utils.logging import get_logger


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    source: str = "yolo"


class YoloDetector:
    """Lazy Ultralytics detector.

    A failed model load no longer kills a processing job outright — frames
    still get read, written, and counted — but it's tracked on `self.error`
    and `self.loaded` so callers (Process.py, Settings.py diagnostics) can
    tell the difference between "this video legitimately has 0 detections"
    and "the detector never loaded, so of course nothing was found."
    Previously this failure was only a console warning, easy to miss
    entirely if the GUI was launched without a visible console.
    """
    def __init__(self, model_path: str = "yolo26n.pt", confidence: float = .75, device: str = "auto"):
        self.model_path, self.confidence, self._model = model_path, confidence, None
        self.device = self._resolve_device(device)
        self.log = get_logger(__name__)
        self.loaded: bool | None = None  # None = not attempted yet
        self.error: str | None = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if self.loaded is False:
            return False  # already failed once this instance — don't retry every frame
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self.loaded = True
            self.log.info("YOLO loaded on device=%s", self.device)
            return True
        except Exception as exc:
            self.loaded = False
            self.error = str(exc)
            self.log.warning("YOLO unavailable (%s); object detection skipped for this session", exc)
            return False

    def detect(self, frame: Any, scale: float = 1.0) -> list[Detection]:
        """Run detection, optionally on a downscaled copy of `frame`.

        `scale < 1.0` (e.g. 0.5) resizes the frame down before inference —
        YOLO's cost scales with input resolution, so detecting on a half-size
        frame is roughly 4x cheaper — then rescales the returned boxes back
        up to the original frame's coordinates, so callers never need to
        think about the scale factor themselves.
        """
        if not self._load():
            return []
        try:
            import cv2
            input_frame = frame
            if scale != 1.0:
                input_frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

            result = self._model(input_frame, conf=self.confidence, verbose=False, device=self.device)[0]
            names = result.names
            inv = 1.0 / scale
            detections = []
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                if scale != 1.0:
                    x1, y1, x2, y2 = x1 * inv, y1 * inv, x2 * inv, y2 * inv
                detections.append(Detection(
                    str(names[int(box.cls[0])]), float(box.conf[0]),
                    (int(x1), int(y1), int(x2), int(y2)),
                ))
            return detections
        except Exception as exc:
            self.log.warning("YOLO inference failed: %s", exc)
            return []
