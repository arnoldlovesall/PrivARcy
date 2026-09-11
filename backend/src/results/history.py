from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class HistoryEntry:
    source_name: str
    processed_at: str
    frames: int
    total_detections: int
    redactions: int
    output_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name, "processed_at": self.processed_at,
            "frames": self.frames, "total_detections": self.total_detections,
            "redactions": self.redactions, "output_path": self.output_path,
        }


class ProcessingHistoryStore:
    """A rolling log of completed processing jobs (file or live), for the
    Home page's "Recent Activity" list. Capped at `max_entries` — this is
    a lightweight in-memory activity feed, not the durable results record
    (see ResultsStore, which holds full per-job detail while a session is
    active)."""

    def __init__(self, max_entries: int = 25):
        self.max_entries = max_entries
        self._entries: list[HistoryEntry] = []

    def record(self, source_name: str, frames: int, total_detections: int,
               redactions: int, output_path: str | None = None) -> HistoryEntry:
        entry = HistoryEntry(
            source_name=source_name,
            processed_at=datetime.now().strftime("%b %d, %Y %I:%M %p"),
            frames=frames, total_detections=total_detections,
            redactions=redactions, output_path=output_path,
        )
        self._entries.insert(0, entry)  # newest first
        del self._entries[self.max_entries:]
        return entry

    def recent(self, limit: int | None = None) -> list[HistoryEntry]:
        return self._entries[:limit] if limit else list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
