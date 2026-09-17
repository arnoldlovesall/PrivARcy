from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TextClassification:
    category: str | None          # PII sub-type, e.g. "payment_card"
    sensitivity: str               # "sensitive" | "benign"
    confidence: float


# Below this weight, a pattern's matches are treated as benign outright —
# CorrectionLogStore.refine_pattern_weights() never produces a weight this
# low from real evidence (its floor is 0.3), so this only kicks in if a
# weight was manually forced lower than the automatic refinement would.
SUPPRESS_BELOW = 0.15


class PrivacyTextClassifier:
    """Rule-based sensitivity classification for OCR-extracted text.

    Deterministic pattern matching (not a learned model) so decisions stay
    auditable: every match is traceable back to a named regex. Text that
    matches none of the PII patterns is treated as benign, non-sensitive
    content (e.g. a street sign, a product label) rather than sensitive PII.

    `pattern_weights` is the correction feedback mechanism's actual
    effect: CorrectionLogStore.refine_pattern_weights() computes these
    from accumulated reviewer decisions, and they scale each pattern's
    match confidence here — a pattern reviewers keep rejecting ends up
    contributing less (or, below SUPPRESS_BELOW, not being treated as
    sensitive at all), without touching the regex patterns themselves or
    retraining any model.
    """

    PATTERNS = {
        # Order matters: more specific patterns are checked first, since
        # the first match wins. A card number is also a "long digit
        # sequence" that the looser phone pattern would match too — with
        # phone checked first, every credit card number used to get
        # mis-categorized as a phone number (CATEGORY_HINTS then routed
        # it to DOCUMENT instead of CREDENTIAL).
        "payment_card": r"\b(?:\d[ -]?){13,19}\b",
        "email": r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
        "government_id": r"\b(?:SSS|TIN|SSN|PASSPORT|DRIVER.?S? LICENSE|DL#)\b",
        "license_plate": r"\b[A-Z]{2,3}[- ]?\d{3,4}\b",
        "date_of_birth": r"\bDOB[:\s]",
        "confidential_marking": r"\b(CONFIDENTIAL|INTERNAL USE ONLY|RESTRICTED|PROPRIETARY)\b",
        "address": r"\b\d{1,5}\s+[A-Za-z0-9.\s]{2,40}\s(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?)\b",
        "person_name": r"\b(?:name[:\s]+|mr\.?|mrs\.?|ms\.?|miss)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
        "phone": r"\b(?:\+?\d[\d ()-]{7,}\d)\b",
    }

    # Maps a matched PII pattern to one of the five review categories, so
    # OCR-derived signals reinforce (or override) the YOLO26 detection label.
    CATEGORY_HINTS = {
        "email": "DOCUMENT",
        "phone": "DOCUMENT",
        "payment_card": "CREDENTIAL",
        "government_id": "ID",
        "license_plate": "LICENSE_PLATE",
        "date_of_birth": "ID",
        "confidential_marking": "DOCUMENT",
        "address": "DOCUMENT",
        "person_name": "DOCUMENT",
    }

    def __init__(self, weights_path: str | Path | None = None):
        self.weights_path = Path(weights_path) if weights_path else None
        self.pattern_weights: dict[str, float] = {}
        if self.weights_path:
            self.load_weights()

    def classify(self, text: str) -> TextClassification:
        if not text or not text.strip():
            return TextClassification(None, "benign", 0.0)
        for category, pattern in self.PATTERNS.items():
            if re.search(pattern, text, re.I):
                weight = self.pattern_weights.get(category, 1.0)
                if weight < SUPPRESS_BELOW:
                    continue  # reviewers have consistently rejected this pattern — treat as benign
                confidence = min(1.0, .95 * weight)
                return TextClassification(category, "sensitive", confidence)
        return TextClassification(None, "benign", .60)

    def category_hint(self, classification: TextClassification) -> str | None:
        if classification.category is None:
            return None
        return self.CATEGORY_HINTS.get(classification.category)

    def load_weights(self, path: str | Path | None = None) -> None:
        path = Path(path) if path else self.weights_path
        if not path:
            return
        try:
            self.pattern_weights = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.pattern_weights = {}

    def save_weights(self, path: str | Path | None = None) -> None:
        path = Path(path) if path else self.weights_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.pattern_weights, indent=2), encoding="utf-8")
