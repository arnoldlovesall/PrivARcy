"""Replaces frontend/Settings.py.

The threshold sliders, redaction-method dropdown, and performance-profile
selector become a GET/PUT pair; "Save" simply persists to disk instead of
writing into an in-memory GUI-only AppConfig.
"""
from fastapi import APIRouter, Depends

from ..deps import get_service
from ..schemas import SettingsUpdateRequest
from src.integration import BackendService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(service: BackendService = Depends(get_service)):
    return service.get_settings()


@router.put("")
def update_settings(payload: SettingsUpdateRequest, service: BackendService = Depends(get_service)):
    updates = payload.model_dump(exclude_none=True)
    if "performance_profile" in updates:
        service.config.apply_performance_profile(updates.pop("performance_profile"))
    return service.update_settings(**updates)


@router.get("/diagnostics")
def diagnostics(service: BackendService = Depends(get_service)):
    """Attempts to load the YOLO detector, TrOCR, and face_recognition —
    reports which actually work, since a missing/broken model otherwise
    fails silently (by design, so a job never crashes because of it) and
    just produces empty results with no visible explanation."""
    return service.diagnostics()
