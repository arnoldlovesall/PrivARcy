from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class CorrectionLogStore:
    """Local SQLite log of human reviewer decisions on flagged detections.

    This is the "correction feedback mechanism": every Confirm/Reject on a
    review item gets logged here, and `refine_pattern_weights()` — run
    periodically, not per-decision — turns the accumulated log into
    updated confidence weights for PrivacyTextClassifier's regex patterns.
    A pattern that reviewers keep rejecting (frequent false positives)
    gets down-weighted; one that's consistently confirmed gets
    reinforced. This improves detection accuracy across sessions *without*
    retraining YOLO26 or TrOCR — it only ever adjusts the rule-based
    classifier's own pattern weights.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT,
                    category TEXT,
                    pattern TEXT,
                    decision TEXT NOT NULL CHECK(decision IN ('confirmed', 'rejected')),
                    logged_at TEXT NOT NULL
                )
            """)

    def log_decision(self, item_id, category: str | None, pattern: str | None, decision: str) -> None:
        """Record one reviewer decision. Silently ignores anything other
        than a final confirmed/rejected decision (e.g. 'pending') — only
        a completed human judgment is useful correction signal."""
        if decision not in ("confirmed", "rejected"):
            return
        pattern = pattern or category
        if not pattern:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO corrections (item_id, category, pattern, decision, logged_at) VALUES (?, ?, ?, ?, ?)",
                (str(item_id), category, pattern, decision, datetime.now().isoformat(timespec="seconds")),
            )

    def pattern_stats(self) -> dict[str, dict[str, int]]:
        """{pattern_name: {"confirmed": n, "rejected": n}} across the
        whole log — the raw evidence refine_pattern_weights() reduces
        into weights."""
        stats: dict[str, dict[str, int]] = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT pattern, decision, COUNT(*) FROM corrections GROUP BY pattern, decision"
            ).fetchall()
        for pattern, decision, count in rows:
            stats.setdefault(pattern, {"confirmed": 0, "rejected": 0})[decision] = count
        return stats

    def refine_pattern_weights(self, min_samples: int = 5) -> dict[str, float]:
        """Compute an updated weight per pattern from the logged corrections.

        Patterns with fewer than `min_samples` total decisions are left
        out entirely (not enough evidence to adjust yet — the caller
        should leave those at their existing/default weight). Confirm
        rate maps to a weight in [0.3, 1.2]: a pattern that's always
        rejected is suppressed but never silenced outright (a rare true
        positive shouldn't be permanently ignored just because it's
        usually wrong in this particular deployment), and a pattern
        that's always confirmed gets a mild boost above 1.0.
        """
        stats = self.pattern_stats()
        weights = {}
        for pattern, counts in stats.items():
            total = counts["confirmed"] + counts["rejected"]
            if total < min_samples:
                continue
            confirm_rate = counts["confirmed"] / total
            weights[pattern] = round(0.3 + confirm_rate * 0.9, 2)
        return weights

    def total_logged(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]

    def recent(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM corrections ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
