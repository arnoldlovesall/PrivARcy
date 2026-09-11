from src.classifiers import PrivacyTextClassifier
from src.config import category_for_label
from src.correction import CorrectionLogStore
from src.dataset import DatasetPipeline
from src.decision import PrivacyDecisionEngine
from src.review import ReviewStore
from src.smoothing import TemporalSmoother
from src.tracker.simple import _iou


def test_text_classifier_identifies_email():
    assert PrivacyTextClassifier().classify("mail a@b.com").category == "email"


def test_text_classifier_benign_text_is_not_sensitive():
    assert PrivacyTextClassifier().classify("OPEN 24 HOURS").sensitivity == "benign"


def test_decision_engine():
    engine = PrivacyDecisionEngine(.8, .4)
    assert engine.decide(.9) == "redact"
    assert engine.decide(.5) == "review"
    assert engine.decide(.1) == "ignore"


def test_decision_engine_confidence_gated_review_overrides():
    engine = PrivacyDecisionEngine(.8, .4)
    # A registered/consented participant is never redacted, even at high confidence.
    assert engine.decide(.95, known_consent=True) == "allow"
    # Sensitive OCR text forces a redact even at low detection confidence.
    assert engine.decide(.5, text_sensitive=True) == "redact"


def test_category_for_label_maps_to_review_boxes():
    assert category_for_label("Faces") == "FACE"
    assert category_for_label("credit card") == "CREDENTIAL"
    assert category_for_label("license plates") == "LICENSE_PLATE"


def test_review_store_groups_into_five_category_boxes():
    store = ReviewStore()
    store.add(label="Face", category="FACE", source="cam", frame=1, time="0.0", confidence=.5)
    store.add(label="ID Card", category="ID", source="cam", frame=2, time="0.1", confidence=.6)
    boxes = store.by_category()
    assert set(boxes) == {"FACE", "ID", "DOCUMENT", "CREDENTIAL", "LICENSE_PLATE"}
    assert len(boxes["FACE"]) == 1
    assert store.pending_count() == 2


def test_bbox_to_yolo_label_is_normalized():
    label = DatasetPipeline.bbox_to_yolo_label(0, (100, 50, 300, 250), 640, 480)
    class_id, cx, cy, w, h = label.split()
    assert class_id == "0"
    assert 0.0 <= float(cx) <= 1.0 and 0.0 <= float(cy) <= 1.0
    assert 0.0 <= float(w) <= 1.0 and 0.0 <= float(h) <= 1.0


def test_temporal_smoother_averages_across_frames():
    smoother = TemporalSmoother(window=3)
    smoother.smooth(1, (0, 0, 100, 100))
    smoother.smooth(1, (10, 10, 110, 110))
    result = smoother.smooth(1, (20, 20, 120, 120))
    assert result == (10, 10, 110, 110)


def test_temporal_smoother_forget_stale_clears_history():
    smoother = TemporalSmoother(window=3)
    smoother.smooth(1, (0, 0, 10, 10))
    smoother.forget_stale(set())
    result = smoother.smooth(1, (50, 50, 60, 60))
    assert result == (50, 50, 60, 60)


def test_temporal_smoother_passthrough_without_track_id():
    smoother = TemporalSmoother(window=5)
    assert smoother.smooth(None, (1, 2, 3, 4)) == (1, 2, 3, 4)


def test_correction_log_refines_pattern_weights(tmp_path):
    store = CorrectionLogStore(tmp_path / "corrections.db")
    for _ in range(8):
        store.log_decision("item", "DOCUMENT", "confidential_marking", "rejected")
    for _ in range(2):
        store.log_decision("item", "DOCUMENT", "confidential_marking", "confirmed")
    for _ in range(9):
        store.log_decision("item", "CREDENTIAL", "payment_card", "confirmed")
    store.log_decision("item", "CREDENTIAL", "payment_card", "rejected")

    weights = store.refine_pattern_weights(min_samples=5)
    assert weights["confidential_marking"] < weights["payment_card"]
    assert weights["payment_card"] > 1.0
    assert store.total_logged() == 20


def test_correction_log_ignores_patterns_below_min_samples(tmp_path):
    store = CorrectionLogStore(tmp_path / "corrections.db")
    store.log_decision("item", "FACE", "email", "confirmed")
    weights = store.refine_pattern_weights(min_samples=5)
    assert "email" not in weights


def test_classifier_suppresses_low_weight_pattern(tmp_path):
    classifier = PrivacyTextClassifier(tmp_path / "weights.json")
    classifier.pattern_weights = {"confidential_marking": 0.1}
    result = classifier.classify("CONFIDENTIAL — do not share")
    assert result.sensitivity == "benign"


def test_classifier_boosts_high_weight_pattern(tmp_path):
    classifier = PrivacyTextClassifier(tmp_path / "weights.json")
    classifier.pattern_weights = {"payment_card": 1.2}
    result = classifier.classify("4111 1111 1111 1111")
    assert result.sensitivity == "sensitive"
    assert result.confidence > 0.95
    assert result.confidence <= 1.0


def test_classifier_weights_persist_across_instances(tmp_path):
    path = tmp_path / "weights.json"
    c1 = PrivacyTextClassifier(path)
    c1.pattern_weights = {"email": 0.5}
    c1.save_weights()

    c2 = PrivacyTextClassifier(path)
    assert c2.pattern_weights == {"email": 0.5}


def test_iou():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
