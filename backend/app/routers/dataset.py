"""Training-data growth for the custom YOLO26 model: Frame Extraction,
Dataset Pipeline status, and data.yaml regeneration. Active learning
itself (confirmed review items -> new training samples) happens
automatically in POST /review/{id}/decision — see BackendService.decide_review_item.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_service
from src.integration import BackendService

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("/status")
def dataset_status(service: BackendService = Depends(get_service)):
    return service.dataset_status()


@router.post("/extract-frames")
def extract_frames(video_path: str, every_n_frames: int = 30,
                    service: BackendService = Depends(get_service)):
    if not Path(video_path).exists():
        raise HTTPException(404, "video_path not found")
    saved = service.extract_frames(video_path, every_n_frames)
    return {"extracted": len(saved), "paths": saved}


@router.post("/regenerate-data-yaml")
def regenerate_data_yaml(service: BackendService = Depends(get_service)):
    path = service.regenerate_data_yaml()
    return {"data_yaml": path}
