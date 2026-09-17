from dataclasses import dataclass


@dataclass
class Decision:
    action: str                 # "allow" | "redact" | "review" | "ignore"
    reason: str


class PrivacyDecisionEngine:
    """Confidence-gated decision logic.

    - >= high  -> auto-redact (no human review needed)
    - < low    -> discard as noise
    - between  -> route to the human Review queue (confidence-gated review)

    Text sensitivity (from the rule-based classifier) and known consent
    (a matched, registered face) can each override the raw detection
    confidence, since a low-confidence box containing a matched SSN pattern
    is still worth redacting, and a high-confidence box of a consented
    participant should never be redacted.
    """

    def __init__(self, high: float = .80, low: float = .50):
        self.high, self.low = high, low

    def decide(self, confidence: float, known_consent: bool = False,
               text_sensitive: bool = False) -> str:
        if known_consent:
            return "allow"
        if text_sensitive or confidence >= self.high:
            return "redact"
        return "review" if confidence >= self.low else "ignore"

    def decide_detailed(self, confidence: float, known_consent: bool = False,
                         text_sensitive: bool = False) -> Decision:
        action = self.decide(confidence, known_consent, text_sensitive)
        reasons = {
            "allow": "matched a registered, consented participant",
            "redact": "text matched a sensitive PII pattern" if text_sensitive
                      else f"confidence {confidence:.2f} >= high threshold {self.high:.2f}",
            "review": f"confidence {confidence:.2f} between low ({self.low:.2f}) and high ({self.high:.2f})",
            "ignore": f"confidence {confidence:.2f} < low threshold {self.low:.2f}",
        }
        return Decision(action, reasons[action])
