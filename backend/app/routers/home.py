"""Replaces frontend/Home.py.

The GUI landing page's cards (pending reviews, registered faces, active
jobs) become a single overview endpoint; the source-selection buttons that
used to route to Process/Live are just those routers' own endpoints now.
"""
from fastapi import APIRouter, Depends

from ..deps import get_service
from src.integration import BackendService

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/overview")
def overview(service: BackendService = Depends(get_service)):
    return service.overview()


@router.get("/history")
def history(limit: int = 10, service: BackendService = Depends(get_service)):
    return service.get_history(limit)
