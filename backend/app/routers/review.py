"""Replaces frontend/Review.py.

The timeline, detail card, and per-item Confirm/Reject buttons become a
queue endpoint plus a decision endpoint. The five featured category boxes
(Faces, ID Cards, Documents, License Plate, Credit/Debit Cards) that used
to be filter chips in the GUI are now GET /review/categories, returning
each box's items and pending/confirmed/rejected counts directly.
"""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_service
from ..schemas import ReviewDecisionRequest
from src.config import REVIEW_CATEGORY_LABELS
from src.integration import BackendService

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue")
def queue(category: str | None = None, service: BackendService = Depends(get_service)):
    store = service.review_queue()
    items = store.all()
    if category:
        items = [i for i in items if i.category == category.upper()]
    return {
        "total": len(items),
        "pending": sum(1 for i in items if i.status == "pending"),
        "items": [i.to_dict() for i in items],
    }


@router.get("/categories")
def categories(service: BackendService = Depends(get_service)):
    """The five 'featured boxes' — Faces, ID Cards, Documents, License
    Plate, and Credit/Debit Cards — each with its item list and counts."""
    store = service.review_queue()
    boxes = store.by_category()
    counts = store.category_counts()
    return {
        code: {
            "label": REVIEW_CATEGORY_LABELS[code],
            **counts[code],
            "items": [i.to_dict() for i in items],
        }
        for code, items in boxes.items()
    }


@router.get("/{item_id}")
def get_item(item_id: int, service: BackendService = Depends(get_service)):
    item = service.review_queue().get(item_id)
    if item is None:
        raise HTTPException(404, "Unknown review item")
    return item.to_dict()


@router.post("/{item_id}/decision")
def decide(item_id: int, payload: ReviewDecisionRequest, service: BackendService = Depends(get_service)):
    try:
        # Also feeds confirmed items into the active-learning dataset and
        # logs the decision to the correction log — see
        # BackendService.decide_review_item / ActiveLearningStore / CorrectionLogStore.
        item = service.decide_review_item(item_id, payload.decision)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if item is None:
        raise HTTPException(404, "Unknown review item")
    return item.to_dict()


@router.post("/refine-classifier")
def refine_classifier(min_samples: int = 5, service: BackendService = Depends(get_service)):
    """The correction feedback mechanism: recomputes PrivacyTextClassifier
    pattern weights from the logged reviewer decisions and persists them.
    Improves detection accuracy across sessions without retraining
    YOLO26/TrOCR — only the rule-based classifier's weights change."""
    return service.refine_classifier(min_samples)
