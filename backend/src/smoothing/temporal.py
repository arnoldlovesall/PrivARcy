from __future__ import annotations

from collections import deque


class TemporalSmoother:
    """Links a tracked object's redaction box across consecutive frames
    so it doesn't visibly jitter/flicker in the output video.

    A raw per-frame detection box wobbles by a few pixels frame-to-frame
    even for a stationary object (normal detector noise) — visible as
    flicker once redacted, since the blur/mask region's edges move
    slightly every frame. This keeps a short rolling window of each
    track's boxes (keyed by IoUTracker's track_id) and returns the
    moving average, which is what actually gets redacted. Detection
    itself, OCR, and the sensitivity decision all still use the raw box —
    only the drawn redaction region is smoothed.
    """

    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self._history: dict[int, deque] = {}

    def smooth(self, track_id: int | None, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if track_id is None:
            return bbox  # nothing to average against across frames
        history = self._history.setdefault(track_id, deque(maxlen=self.window))
        history.append(bbox)
        n = len(history)
        x1 = sum(b[0] for b in history) / n
        y1 = sum(b[1] for b in history) / n
        x2 = sum(b[2] for b in history) / n
        y2 = sum(b[3] for b in history) / n
        return (int(x1), int(y1), int(x2), int(y2))

    def forget_stale(self, active_track_ids: set[int]) -> None:
        """Drop history for tracks no longer active, so memory doesn't
        grow unbounded over a long video/live session."""
        for track_id in list(self._history):
            if track_id not in active_track_ids:
                del self._history[track_id]
