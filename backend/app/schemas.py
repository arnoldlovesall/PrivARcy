"""Pydantic request/response models for every router."""
from __future__ import annotations

from pydantic import BaseModel, Field


# -- Process ---------------------------------------------------------------
class StartProcessingRequest(BaseModel):
    video_path: str = Field(..., description="Server-side path returned by POST /process/upload")
    confidence_threshold: float | None = None
    low_threshold: float | None = None
    redaction_method: str | None = Field(None, description="blur | pixelate | solid mask")
    blur_strength: int | None = None
    source_name: str | None = None


# -- Review ------------------------------------------------------------------
class ReviewDecisionRequest(BaseModel):
    decision: str = Field(..., description="confirmed | rejected | pending")


# -- Faces ---------------------------------------------------------------------
class FaceRegisterResponse(BaseModel):
    code: str
    name: str
    image_path: str


# -- Live --------------------------------------------------------------------
class LiveStartRequest(BaseModel):
    camera_index: int
    width: int | None = None
    height: int | None = None
    fps: int | None = None


# -- Settings ------------------------------------------------------------------
class SettingsUpdateRequest(BaseModel):
    confidence_threshold: float | None = None
    low_threshold: float | None = None
    iou_threshold: float | None = None
    temporal_smoothing: int | None = None
    track_termination: int | None = None
    redaction_method: str | None = None
    blur_strength: int | None = None
    performance_profile: str | None = None
    enabled_classes: list[str] | None = None
    model_path: str | None = None
    ocr_model_path: str | None = None
