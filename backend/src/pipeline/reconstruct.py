from __future__ import annotations

from collections import defaultdict

from ..config import AppConfig
from ..redaction import RedactionEngine
from ..smoothing import TemporalSmoother
from ..video import VideoReader, VideoWriter


def should_redact_event(event: dict) -> bool:
    """Final-output rule: auto-redacts plus reviewer-confirmed medium items."""
    if not event.get("bbox"):
        return False
    if event.get("action") == "redact":
        return True
    return event.get("action") == "review" and event.get("status") == "confirmed"


def reconstruct_redacted_video(
    source_path: str,
    output_path: str,
    detections: list[dict],
    config: AppConfig | None = None,
) -> str:
    """Re-read the original video and burn in auto-redacts plus confirmed reviews.

    The first processing pass writes a draft that only auto-redacts high-confidence
    regions. After the post-session review queue is resolved, this rebuilds the
    shareable file so Confirm actually appears in the exported MP4.
    """
    config = config or AppConfig()
    by_frame: dict[int, list[dict]] = defaultdict(list)
    for event in detections:
        if should_redact_event(event):
            by_frame[int(event["frame"])].append(event)

    reader = VideoReader(source_path)
    writer = None
    smoother = TemporalSmoother(config.temporal_smoothing)
    redactor = RedactionEngine(config.redaction_method, config.blur_strength)
    try:
        for index, frame in enumerate(reader, 1):
            if writer is None:
                writer = VideoWriter(output_path, reader.fps, (frame.shape[1], frame.shape[0]))
            regions = []
            for event in by_frame.get(index, []):
                bbox = tuple(event["bbox"])
                regions.append(smoother.smooth(event.get("track_id"), bbox))
            writer.write(redactor.apply(frame, regions))
    finally:
        reader.close()
        if writer:
            writer.close()
    return str(output_path)
