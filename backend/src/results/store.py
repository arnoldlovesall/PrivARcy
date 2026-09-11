from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import REVIEW_CATEGORIES, REVIEW_CATEGORY_LABELS


@dataclass
class JobResults:
    job_id: str
    output_path: str | None = None
    video_duration: str | None = None
    processing_time: str | None = None
    frames_processed: int = 0
    total_redactions: int = 0
    categories: dict[str, int] = field(default_factory=lambda: {c: 0 for c in REVIEW_CATEGORIES})
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "output_path": self.output_path,
            "video_duration": self.video_duration,
            "processing_time": self.processing_time,
            "frames_processed": self.frames_processed,
            "total_redactions": self.total_redactions,
            "categories": {REVIEW_CATEGORY_LABELS[c]: n for c, n in self.categories.items()},
            "summary": self.summary,
        }


class ResultsStore:
    """Holds the latest results per processing job. Replaces the PyQt
    ResultsPage's set_results()/export_video()/reset() with a plain store
    the API layer reads and the /results/export endpoint serves from."""

    def __init__(self):
        self._results: dict[str, JobResults] = {}

    def set(self, job_id: str, **fields: Any) -> JobResults:
        result = self._results.get(job_id) or JobResults(job_id=job_id)
        for key, value in fields.items():
            if hasattr(result, key) and value is not None:
                setattr(result, key, value)
        self._results[job_id] = result
        return result

    def get(self, job_id: str) -> JobResults | None:
        return self._results.get(job_id)

    def latest(self) -> JobResults | None:
        return next(reversed(self._results.values()), None) if self._results else None

    def reset(self, job_id: str | None = None) -> None:
        if job_id is None:
            self._results.clear()
        else:
            self._results.pop(job_id, None)
