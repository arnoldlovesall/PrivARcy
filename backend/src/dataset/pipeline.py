from __future__ import annotations

import random
import shutil
from pathlib import Path

from .data_yaml import DEFAULT_CLASS_NAMES, write_data_yaml


class DatasetPipeline:
    """Owns the on-disk YOLO training set: directory layout, adding a
    labeled sample, train/val split, and regenerating data.yaml.

    This is what turns loose (image, YOLO-format label) pairs — coming
    from FrameExtractor + manual labeling, or from ActiveLearningStore —
    into a directory `ultralytics` can train directly against.
    """

    def __init__(self, dataset_dir: str | Path, class_names: list[str] | None = None):
        self.dataset_dir = Path(dataset_dir)
        self.class_names = class_names or DEFAULT_CLASS_NAMES
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for split in ("train", "val"):
            (self.dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    def add_sample(self, image_path: str | Path, yolo_label_lines: list[str],
                   split: str | None = None, val_fraction: float = 0.15) -> str:
        """Copy an image + its YOLO-format label lines into the dataset.

        `yolo_label_lines` are already-formatted `"class_id cx cy w h"`
        strings (normalized 0-1) — one per object in the image. `split`
        picks train/val explicitly; otherwise it's assigned randomly at
        `val_fraction`, which is the usual way to grow a dataset
        incrementally without hand-curating a validation set every time.
        """
        image_path = Path(image_path)
        split = split or ("val" if random.random() < val_fraction else "train")

        dest_image = self.dataset_dir / "images" / split / image_path.name
        shutil.copyfile(image_path, dest_image)

        label_path = self.dataset_dir / "labels" / split / (image_path.stem + ".txt")
        label_path.write_text("\n".join(yolo_label_lines) + "\n", encoding="utf-8")
        return split

    def counts(self) -> dict:
        return {
            split: len(list((self.dataset_dir / "images" / split).glob("*")))
            for split in ("train", "val")
        }

    def regenerate_data_yaml(self) -> Path:
        return write_data_yaml(self.dataset_dir, self.class_names)

    @staticmethod
    def bbox_to_yolo_label(class_id: int, bbox: tuple[int, int, int, int],
                            image_width: int, image_height: int) -> str:
        """Convert a pixel (x1, y1, x2, y2) box — PrivARcy's Detection
        format everywhere else in the codebase — into a normalized YOLO
        label line `"class_id cx cy w h"`."""
        x1, y1, x2, y2 = bbox
        cx = ((x1 + x2) / 2) / image_width
        cy = ((y1 + y2) / 2) / image_height
        w = (x2 - x1) / image_width
        h = (y2 - y1) / image_height
        return f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
