"""Replaces frontend/FaceRegister.py.

The photo file-picker becomes an upload endpoint; the participant grid,
Remove button, and verification dialog become list/delete/verify
endpoints. Registration still rejects photos with zero or multiple faces
instead of pretending enrollment happened.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from ..deps import get_service
from src.integration import BackendService

router = APIRouter(prefix="/faces", tags=["faces"])

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tiff"}


@router.get("")
def list_faces(service: BackendService = Depends(get_service)):
    return service.list_faces()


@router.post("/register")
async def register_face(name: str, file: UploadFile, service: BackendService = Depends(get_service)):
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported image type '{ext}'")

    existing = len(service.list_faces())
    code = f"P-{existing + 1:03d}"
    dest = service.config.registry_dir / f"{code}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        result = service.register_face(code, name, str(dest))
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc))
    result["registered_at"] = datetime.now().isoformat(timespec="seconds")
    return result


@router.delete("/{code}")
def remove_face(code: str, service: BackendService = Depends(get_service)):
    service.remove_face(code)
    return {"code": code, "removed": True}


@router.post("/{code}/verify")
def verify_face(code: str, service: BackendService = Depends(get_service)):
    result = service.verify_face(code)
    if result["confidence"] == 0.0 and "No such" in result["message"]:
        raise HTTPException(404, result["message"])
    return result
