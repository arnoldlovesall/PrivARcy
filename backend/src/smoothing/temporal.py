from __future__ import annotations


class TemporalSmoother:
    """Stabilizes redaction boxes across frames with an exponential moving average.

    Chapter 3 specifies IoU tracking plus EMA coordinate updates so a box does
    not flicker when the detector jitters by a few pixels. Detection, OCR, and
    the sensitivity decision still use the raw box; only the drawn region is
    smoothed.

    `window` is the EMA span: alpha = 2 / (window + 1), the standard conversion
    from a trailing-window length to an EMA smoothing factor.
    """

    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self.alpha = 2.0 / (self.window + 1)
        self._ema: dict[int, tuple[float, float, float, float]] = {}

    def smooth(self, track_id: int | None, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if track_id is None:
            return bbox
        if track_id not in self._ema:
            self._ema[track_id] = tuple(float(v) for v in bbox)
            return bbox
        prev = self._ema[track_id]
        alpha = self.alpha
        updated = tuple(alpha * n + (1.0 - alpha) * p for n, p in zip(bbox, prev))
        self._ema[track_id] = updated
        return tuple(int(round(v)) for v in updated)

    def forget_stale(self, active_track_ids: set[int]) -> None:
        """Drop EMA state for tracks that are no longer active."""
        for track_id in list(self._ema):
            if track_id not in active_track_ids:
                del self._ema[track_id]
