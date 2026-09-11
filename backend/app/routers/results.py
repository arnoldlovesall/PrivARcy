"""Replaces frontend/Results.py.

The summary cards (precision/recall/F1/FPS/detections), the category
breakdown, and the Export MP4 / Process Another Video buttons become plain
GET / download / reset endpoints.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..deps import get_service
from src.integration import BackendService

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{job_id}")
def get_results(job_id: str, service: BackendService = Depends(get_service)):
    result = service.results().get(job_id)
    if result is None:
        raise HTTPException(404, "No results for this job_id yet")
    return result.to_dict()


@router.get("/{job_id}/export")
def export_video(job_id: str, service: BackendService = Depends(get_service)):
    result = service.results().get(job_id)
    if result is None or not result.output_path:
        raise HTTPException(404, "No redacted output available for this job_id")
    path = Path(result.output_path)
    if not path.exists():
        raise HTTPException(404, f"Output file missing on disk: {path}")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.post("/reset")
def reset_session(service: BackendService = Depends(get_service)):
    """Backs the 'Process Another Video' action: clears results + review queue."""
    service.reset_session()
    return {"reset": True}
