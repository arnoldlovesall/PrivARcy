"""Replaces frontend/Live.py.

Camera discovery, the Start/Stop toggle, the preview panel, live stats,
and the audit log — all previously driven by a QTimer polling loop inside
the GUI thread — become endpoints backed by a real LiveSession running its
own background thread, so the pipeline keeps running even with no client
connected.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from ..deps import get_service
from ..schemas import LiveStartRequest
from src.integration import BackendService

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/cameras")
def list_cameras(service: BackendService = Depends(get_service)):
    return service.discover_cameras()


@router.post("/start")
def start_live(payload: LiveStartRequest, service: BackendService = Depends(get_service)):
    if not service.start_live(payload.camera_index, payload.width, payload.height, payload.fps):
        raise HTTPException(400, f"Could not open camera index {payload.camera_index}")
    return {"live": True, "camera_index": payload.camera_index}


@router.post("/stop")
def stop_live(service: BackendService = Depends(get_service)):
    service.stop_live()
    return {"live": False}


@router.get("/frame")
def latest_frame(service: BackendService = Depends(get_service)):
    session = service.live_session
    if session is None or not session.is_live:
        raise HTTPException(404, "No live session running")
    frame = session.latest_frame_jpeg()
    if frame is None:
        raise HTTPException(202, "Live session starting, no frame yet")
    return Response(content=frame, media_type="image/jpeg")


@router.get("/stats")
def live_stats(service: BackendService = Depends(get_service)):
    session = service.live_session
    if session is None:
        return {"live": False}
    return {
        "live": session.is_live,
        "elapsed_seconds": session.elapsed_seconds(),
        "requested_resolution": session.requested_resolution,
        "actual_resolution": session.actual_resolution,
        **session.stats,
    }


@router.get("/audit-log")
def audit_log(service: BackendService = Depends(get_service)):
    session = service.live_session
    return session.audit_log if session else []
