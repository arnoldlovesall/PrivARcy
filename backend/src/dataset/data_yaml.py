from __future__ import annotations

from pathlib import Path

# The five privacy classes PrivARcy's custom YOLO26 model is trained to
# detect — matches the review category boxes (Faces/ID Cards/Documents/
# Credit-Debit Cards/License Plate) so a detection's raw class index maps
# straight onto config.category_for_label() with no extra translation step.
DEFAULT_CLASS_NAMES = ["face", "id_card", "document", "credit_card", "license_plate"]


def write_data_yaml(dataset_dir: str | Path, class_names: list[str] | None = None,
                     path: str | Path | None = None) -> Path:
    """Write an Ultralytics-format data.yaml pointing at this dataset.

    Expects the standard YOLO directory layout under `dataset_dir`:
        images/train, images/val, labels/train, labels/val
    (DatasetPipeline.ensure_layout() creates this.) `ultralytics` reads
    this file directly for `yolo train data=data.yaml ...`.
    """
    dataset_dir = Path(dataset_dir)
    class_names = class_names or DEFAULT_CLASS_NAMES
    path = Path(path) if path else dataset_dir / "data.yaml"

    names_block = "\n".join(f"  {i}: {name}" for i, name in enumerate(class_names))
    content = (
        f"path: {dataset_dir.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(class_names)}\n"
        f"names:\n{names_block}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path
