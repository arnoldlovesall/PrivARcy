"""Process-wide singleton BackendService, shared by every router.

FastAPI's dependency injection resolves `get_service` once per request but
always returns the same underlying object, mirroring how the PyQt app
passed one `self._backend` instance into every page.
"""
from __future__ import annotations

from src.integration import BackendService

_service = BackendService()


def get_service() -> BackendService:
    return _service
