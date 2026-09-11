"""Replaces frontend/Process.py.

The file picker becomes a plain multipart upload; the confidence slider,
redaction-method dropdown, and Start/Cancel buttons become request fields
and job-control endpoints. Progress polling (frames/fps/detected/flagged/
ETA) that the GUI drove via worker signals is now GET /process/status/{id}.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from ..deps import get_service
from ..schemas import StartProcessingRequest
from src.integration import BackendService

router = APIRouter(prefix="/process", tags=["process"])

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


@router.post("/upload")
async def upload_video(file: UploadFile, service: BackendService = Depends(get_service)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    dest = service.config.uploads_dir / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"video_path": str(dest), "filename": file.filename, "size_bytes": dest.stat().st_size}


@router.post("/start")
def start_processing(payload: StartProcessingRequest, service: BackendService = Depends(get_service)):
    if not Path(payload.video_path).exists():
        raise HTTPException(404, "video_path not found; upload it first via POST /process/upload")

    overrides = payload.model_dump(exclude={"video_path", "source_name"}, exclude_none=True)
    if overrides:
        service.config.update(**overrides)

    worker = service.start_processing(payload.video_path, payload.source_name)
    return {"job_id": worker.job_id, "state": worker.state}


@router.get("/status/{job_id}")
def job_status(job_id: str, service: BackendService = Depends(get_service)):
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job_id")
    return job.status()


@router.post("/cancel/{job_id}")
def cancel_job(job_id: str, service: BackendService = Depends(get_service)):
    if not service.cancel_job(job_id):
        raise HTTPException(404, "Unknown job_id")
    return {"job_id": job_id, "cancelled": True}


@router.get("")
def list_jobs(service: BackendService = Depends(get_service)):
    return service.list_jobs()
