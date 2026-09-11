from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SETTINGS_PATH = BACKEND_DIR / "data" / "settings.json"

# The five review categories surfaced as "boxes" on the Review queue.
# Every YOLO26 detection class is normalized into one of these.
REVIEW_CATEGORIES = ["FACE", "ID", "DOCUMENT", "CREDENTIAL", "LICENSE_PLATE"]

REVIEW_CATEGORY_LABELS = {
    "FACE": "Faces",
    "ID": "ID Cards",
    "DOCUMENT": "Documents",
    "CREDENTIAL": "Credit / Debit Cards",
    "LICENSE_PLATE": "License Plate",
}

DETECTION_CLASS_TO_CATEGORY = {
    "faces": "FACE",
    "face": "FACE",
    "ids": "ID",
    "id card": "ID",
    "id_card": "ID",
    "documents": "DOCUMENT",
    "document": "DOCUMENT",
    "credentials": "CREDENTIAL",
    "credit card": "CREDENTIAL",
    "debit card": "CREDENTIAL",
    "payment card": "CREDENTIAL",
    "license plates": "LICENSE_PLATE",
    "license plate": "LICENSE_PLATE",
    "screens": "DOCUMENT",
}

PERFORMANCE_PRESETS = {
    "low": {"detection_interval": 15, "jpeg_quality": 60},
    "balanced": {"detection_interval": 5, "jpeg_quality": 80},
    "high": {"detection_interval": 1, "jpeg_quality": 95},
}


@dataclass
class AppConfig:
    """Portable settings used by every backend service.

    Superset of the values previously scattered across the Settings/Process
    GUI pages: pipeline thresholds, tracking, redaction style, performance
    profile, JPEG quality, and which privacy classes are enabled.
    """
    # -- Detection / OCR model paths --
    model_path: str = "yolo26n.pt"
    ocr_model_path: str = "microsoft/trocr-base-printed"
    # "auto" picks CUDA if a GPU + CUDA-enabled torch are available, else
    # CPU. Set explicitly to force one or the other.
    device: str = "auto"
    # Downscales frames before YOLO inference (e.g. 0.5 = half resolution)
    # then rescales boxes back up — inference cost scales with input
    # resolution, so this is one of the biggest single levers for live-
    # stream lag on CPU. 1.0 = no downscaling.
    detection_scale: float = 1.0
    # How many detection passes a tracked object's OCR/classification
    # result stays cached before it's re-run. TrOCR is the single most
    # expensive step per detection — an ID card held up to the camera
    # keeps the same tracked ID across many frames, so re-running OCR on
    # every single detection pass for it is almost pure waste.
    ocr_cache_passes: int = 20

    # -- Confidence-gated decision thresholds (T_high / T_low) --
    confidence_threshold: float = .75      # T_high: >= this -> auto-redact
    low_threshold: float = .40             # T_low: below this -> ignore as noise
    iou_threshold: float = .50
    temporal_smoothing: int = 5
    track_termination: int = 15

    # -- Redaction --
    redaction_method: str = "blur"          # blur | pixelate | solid mask
    blur_strength: int = 31

    # -- Live camera capture resolution/frame rate --
    # Requested, not guaranteed — many webcams silently ignore unsupported
    # combinations (esp. 4K or 60fps) and fall back to their own default.
    # LiveSession reads back what was actually granted after requesting.
    camera_width: int = 1920
    camera_height: int = 1080
    camera_fps: int = 60

    # -- Performance profile --
    performance_profile: str = "balanced"   # low | balanced | high
    detection_interval: int = 5
    jpeg_quality: int = 80

    # -- Enabled detection/privacy classes --
    enabled_classes: set[str] = field(default_factory=lambda: {
        "faces", "ids", "credentials", "documents", "screens", "license plates",
    })

    # -- Storage --
    output_dir: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "output")
    registry_dir: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "face_registry")
    uploads_dir: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "uploads")
    review_frames_dir: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "review_frames")
    dataset_dir: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "dataset")
    correction_log_path: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "correction_log.db")
    classifier_weights_path: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "classifier_weights.json")

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.review_frames_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.correction_log_path.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    def apply_performance_profile(self, profile: str) -> None:
        preset = PERFORMANCE_PRESETS.get(profile)
        if preset:
            self.performance_profile = profile
            self.detection_interval = preset["detection_interval"]
            self.jpeg_quality = preset["jpeg_quality"]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["enabled_classes"] = sorted(self.enabled_classes)
        data["output_dir"] = str(self.output_dir)
        data["registry_dir"] = str(self.registry_dir)
        data["uploads_dir"] = str(self.uploads_dir)
        data["review_frames_dir"] = str(self.review_frames_dir)
        data["dataset_dir"] = str(self.dataset_dir)
        data["correction_log_path"] = str(self.correction_log_path)
        data["classifier_weights_path"] = str(self.classifier_weights_path)
        return data

    def update(self, **kwargs) -> None:
        """Apply a partial update (e.g. from PUT /settings) in place."""
        for key, value in kwargs.items():
            if value is None or not hasattr(self, key):
                continue
            if key == "enabled_classes" and isinstance(value, (list, set, tuple)):
                value = set(value)
            setattr(self, key, value)

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        path = path or SETTINGS_PATH
        config = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config
        for key in ("output_dir", "registry_dir", "uploads_dir", "review_frames_dir", "dataset_dir",
                    "correction_log_path", "classifier_weights_path"):
            data.pop(key, None)
        config.update(**data)
        return config


def category_for_label(label: str) -> str:
    """Map a raw YOLO26 class label to one of the five review categories."""
    return DETECTION_CLASS_TO_CATEGORY.get(label.strip().lower(), "DOCUMENT")
