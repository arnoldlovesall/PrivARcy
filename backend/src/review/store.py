from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import count
from typing import Any

from ..config import REVIEW_CATEGORIES

_ids = count(1)


@dataclass
class ReviewItem:
    """One confidence-gated detection awaiting (or past) human review.

    `category` is always one of the five review "boxes": FACE, ID,
    DOCUMENT, CREDENTIAL, LICENSE_PLATE.
    """
    id: int
    label: str
    category: str
    source: str
    frame: int
    time: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None
    image_path: str | None = None
    ocr_text: str | None = None
    classification: str | None = None
    classification_confidence: float | None = None
    status: str = "pending"  # pending | confirmed | rejected

    def to_dict(self) -> dict:
        return asdict(self)


class ReviewStore:
    """In-memory review queue, grouped into the five category boxes.

    Replaces the PyQt ReviewPage's `self.queue` list plus its
    set_detections()/clear_detections()/handle_decision() methods with a
    plain backend-owned store the API routers read and mutate.
    """

    def __init__(self):
        self._items: dict[int, ReviewItem] = {}

    def clear(self) -> None:
        self._items.clear()

    def add(self, **fields: Any) -> ReviewItem:
        item = ReviewItem(id=next(_ids), **fields)
        self._items[item.id] = item
        return item

    def set_all(self, items: list[ReviewItem]) -> None:
        self._items = {i.id: i for i in items}

    def all(self) -> list[ReviewItem]:
        return sorted(self._items.values(), key=lambda i: i.frame)

    def get(self, item_id: int) -> ReviewItem | None:
        return self._items.get(item_id)

    def decide(self, item_id: int, decision: str) -> ReviewItem | None:
        item = self._items.get(item_id)
        if item is None:
            return None
        if decision not in ("confirmed", "rejected", "pending"):
            raise ValueError("decision must be 'confirmed', 'rejected', or 'pending'")
        item.status = decision
        return item

    def pending_count(self) -> int:
        return sum(1 for i in self._items.values() if i.status == "pending")

    def by_category(self) -> dict[str, list[ReviewItem]]:
        """The five 'featured boxes': Faces, ID Cards, Documents, License
        Plate, and Credit/Debit Cards, each with their own item list."""
        boxes = {cat: [] for cat in REVIEW_CATEGORIES}
        for item in self.all():
            boxes.setdefault(item.category, []).append(item)
        return boxes

    def category_counts(self) -> dict[str, dict[str, int]]:
        counts = {}
        for cat, items in self.by_category().items():
            counts[cat] = {
                "total": len(items),
                "pending": sum(1 for i in items if i.status == "pending"),
                "confirmed": sum(1 for i in items if i.status == "confirmed"),
                "rejected": sum(1 for i in items if i.status == "rejected"),
            }
        return counts
