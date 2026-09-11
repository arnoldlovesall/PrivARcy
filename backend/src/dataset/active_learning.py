from __future__ import annotations

from ..utils.logging import get_logger
from .pipeline import DatasetPipeline

log = get_logger(__name__)

# Review category -> training class id (matches DEFAULT_CLASS_NAMES order).
CATEGORY_TO_CLASS_ID = {
    "FACE": 0, "ID": 1, "DOCUMENT": 2, "CREDENTIAL": 3, "LICENSE_PLATE": 4,
}


class ActiveLearningStore:
    """Closes the confidence-gated review loop back into training data.

    A detection only reaches the human Review queue when the model itself
    was *uncertain* about it (Tlow <= confidence < Thigh) — exactly the
    cases a retrained model would benefit most from seeing labeled
    examples of. When a reviewer confirms one, that's a human-verified
    label for precisely the kind of input the current model struggles
    with, so it gets added straight into the training dataset via
    DatasetPipeline instead of being discarded once the redaction
    decision is made.

    Confirmed only, not rejected — a false positive doesn't have a
    correct bounding box to train on. (Feeding rejected detections back
    as hard negatives is a reasonable follow-up, not implemented here.)
    """

    def __init__(self, dataset_pipeline: DatasetPipeline):
        self.pipeline = dataset_pipeline

    def record_confirmed(self, review_item) -> bool:
        """Add a confirmed ReviewItem to the training set. Returns False
        (not an error) if the item lacks what's needed — e.g. no saved
        frame image, which happens for detections that were auto-redacted
        outright and never routed through review in the first place."""
        if review_item.status != "confirmed":
            return False
        if not review_item.image_path or not review_item.bbox:
            log.info("Skipping active-learning sample for item %s: no saved frame/bbox", review_item.id)
            return False
        return self._add(review_item.image_path, review_item.bbox, review_item.category, review_item.id)

    def record_confirmed_dict(self, item: dict) -> bool:
        """Same as record_confirmed, but for a plain dict — the shape
        Review.py's GUI queue uses (versus ReviewStore's ReviewItem
        dataclass, used by the FastAPI /review endpoints)."""
        if item.get("status") != "confirmed":
            return False
        if not item.get("image_path") or not item.get("bbox"):
            log.info("Skipping active-learning sample for item %s: no saved frame/bbox", item.get("id"))
            return False
        return self._add(item["image_path"], item["bbox"], item.get("category"), item.get("id"))

    def _add(self, image_path: str, bbox: tuple, category: str | None, item_id) -> bool:
        class_id = CATEGORY_TO_CLASS_ID.get(category)
        if class_id is None:
            return False
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
        except (OSError, ImportError) as exc:
            log.warning("Could not read image for active learning: %s", exc)
            return False

        label_line = DatasetPipeline.bbox_to_yolo_label(class_id, bbox, width, height)
        self.pipeline.add_sample(image_path, [label_line])
        log.info("Added confirmed review item %s to training set (%s)", item_id, category)
        return True
