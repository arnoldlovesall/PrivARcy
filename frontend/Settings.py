# Settings.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QSlider, QComboBox,
                             QCheckBox, QGridLayout, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal
import styles
from components import (retheme_widget_tree, NotificationBanner, create_scrollable_container,
                        create_blurred_preview_pixmap, create_solid_mask_preview_pixmap)

PERFORMANCE_PRESETS = {
    "Low-spec / Fastest": {"interval": 15, "jpeg": 60},
    "Balanced": {"interval": 5, "jpeg": 80},
    "High Quality": {"interval": 1, "jpeg": 95},
}

DETECTION_CLASSES = ["Faces", "ID Cards", "Credit / Debit Cards", "Documents", "Screens", "License Plate"]

# UI label <-> backend AppConfig value, for the two OptionCard groups.
REDACTION_STYLE_TO_CONFIG = {"Gaussian Blur": "blur", "Solid Mask": "solid mask"}
CONFIG_TO_REDACTION_STYLE = {v: k for k, v in REDACTION_STYLE_TO_CONFIG.items()}

PERFORMANCE_PROFILE_TO_CONFIG = {"Low-spec / Fastest": "low", "Balanced": "balanced", "High Quality": "high"}
CONFIG_TO_PERFORMANCE_PROFILE = {v: k for k, v in PERFORMANCE_PROFILE_TO_CONFIG.items()}

# UI checkbox label <-> backend AppConfig.enabled_classes entry.
DETECTION_CLASS_TO_CONFIG = {
    "Faces": "faces", "ID Cards": "ids", "Credit / Debit Cards": "credentials",
    "Documents": "documents", "Screens": "screens", "License Plate": "license plates",
}


def group_card(title, hint=None):
    """A titled card used to visually separate each settings sub-section."""
    card = QFrame()
    card.setObjectName("SettingsGroup")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    title_lbl = QLabel(title)
    title_lbl.setObjectName("GroupTitle")
    layout.addWidget(title_lbl)

    if hint:
        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("GroupHint")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

    return card, layout


class OptionCard(QFrame):
    """A clickable, exclusively-selectable card with an optional visual swatch."""
    clicked = pyqtSignal(object)

    def __init__(self, title, desc, custom_pixmap=None, parent=None):
        super().__init__(parent)
        self.setObjectName("OptionCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.value = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        if custom_pixmap is not None:
            self.swatch = QLabel()
            self.swatch.setFixedHeight(54)
            self.swatch.setAlignment(Qt.AlignCenter)
            self.swatch.setPixmap(custom_pixmap)
            styles.themed(self.swatch, lambda: f"border-radius: 8px; border: 1px solid {styles.BORDER_COLOR};")
            layout.addWidget(self.swatch)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        styles.themed(desc_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

    def set_selected(self, selected):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self)
        super().mousePressEvent(event)


class ScrollableSlider(QSlider):
    """Slider that deliberately ignores mouse-wheel input."""
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def wheelEvent(self, event):
        event.ignore()


class SettingSlider(QWidget):
    """An interactive setting slider with title, description, and dynamic live value badge."""
    def __init__(self, title, desc, min_val, max_val, init_val, format_fn):
        super().__init__()
        self.format_fn = format_fn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.val_lbl = QLabel(self.format_fn(init_val))
        styles.themed(self.val_lbl, lambda: f"color: {styles.ACCENT_TEAL}; font-weight: bold; font-size: 13px;")
        self.val_lbl.setAlignment(Qt.AlignRight)

        header_row.addWidget(title_lbl)
        header_row.addStretch()
        header_row.addWidget(self.val_lbl)
        layout.addLayout(header_row)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("GroupHint")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Use ScrollableSlider instead of QSlider
        self.slider = ScrollableSlider(Qt.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(init_val)
        self.slider.valueChanged.connect(self._on_value_change)
        layout.addWidget(self.slider)

    def _on_value_change(self, v):
        self.val_lbl.setText(self.format_fn(v))

    def value(self):
        return self.slider.value()

    def setValue(self, v):
        self.slider.setValue(v)


class SettingsPage(QWidget):
    def __init__(self, backend):
        super().__init__()
        self._backend = backend
        cfg = self._backend.config

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(20)

        heading = QLabel("Pipeline & Model Settings")
        heading.setStyleSheet("font-size: 20px; font-weight: 700;")
        main_layout.addWidget(heading)

        # ---------------- 1. Pipeline Configuration ----------------
        pipe_card, pipe_layout = group_card(
            "Pipeline Configuration",
            "Configure confidence thresholds, temporal stability, and multi-frame tracking."
        )

        # High Threshold (T_high)
        self.t_high_slider = SettingSlider(
            "High Threshold (T_high)",
            "Detections scoring above this value are automatically redacted with no review.",
            min_val=0, max_val=100, init_val=round(cfg.confidence_threshold * 100),
            format_fn=lambda v: f"{v/100:.2f} ({v}%)"
        )
        pipe_layout.addWidget(self.t_high_slider)

        # Low Threshold (T_low)
        self.t_low_slider = SettingSlider(
            "Low Threshold (T_low)",
            "Detections scoring below this value are discarded as noise.",
            min_val=0, max_val=100, init_val=round(cfg.low_threshold * 100),
            format_fn=lambda v: f"{v/100:.2f} ({v}%)"
        )
        pipe_layout.addWidget(self.t_low_slider)

        # Temporal Smoothing
        self.smoothing_slider = SettingSlider(
            "Temporal Smoothing",
            "Controls how detection results are stabilized across multiple frames.",
            min_val=1, max_val=15, init_val=cfg.temporal_smoothing,
            format_fn=lambda v: f"{v} frames window"
        )
        pipe_layout.addWidget(self.smoothing_slider)

        # IoU Match Threshold
        self.iou_slider = SettingSlider(
            "IoU Match Threshold",
            "Defines how much overlap counts as \"the same object\" between frames.",
            min_val=10, max_val=90, init_val=round(cfg.iou_threshold * 100),
            format_fn=lambda v: f"{v/100:.2f} IoU"
        )
        pipe_layout.addWidget(self.iou_slider)

        # Track Termination
        self.track_term_slider = SettingSlider(
            "Track Termination",
            "Number of frames a tracked object can remain undetected before its track ends.",
            min_val=1, max_val=60, init_val=cfg.track_termination,
            format_fn=lambda v: f"{v} frames"
        )
        pipe_layout.addWidget(self.track_term_slider)

        main_layout.addWidget(pipe_card)

        # ---------------- 2. Redaction Style ----------------
        style_card, style_layout = group_card(
            "Redaction Style",
            "How flagged regions are visually obscured in the output video."
        )
        style_row = QHBoxLayout()
        style_row.setSpacing(15)

        self.blur_option = OptionCard(
            "Gaussian Blur",
            "Softens the region so it's unreadable but the scene still reads naturally.",
            custom_pixmap=create_blurred_preview_pixmap(240, 52)
        )
        self.mask_option = OptionCard(
            "Solid Mask",
            "Covers the region completely with a solid black mask — maximum certainty.",
            custom_pixmap=create_solid_mask_preview_pixmap(240, 52)
        )
        self.redaction_style_options = [self.blur_option, self.mask_option]
        for opt in self.redaction_style_options:
            opt.clicked.connect(self.select_redaction_style)
        initial_style = CONFIG_TO_REDACTION_STYLE.get(cfg.redaction_method, "Gaussian Blur")
        for opt in self.redaction_style_options:
            opt.set_selected(opt.value == initial_style)

        style_row.addWidget(self.blur_option)
        style_row.addWidget(self.mask_option)
        style_layout.addLayout(style_row)
        main_layout.addWidget(style_card)

        # ---------------- 3. Performance Profile ----------------
        perf_card, perf_layout = group_card(
            "Performance Profile",
            "Picking a profile automatically tunes the frame-sampling interval and output quality."
        )
        perf_row = QHBoxLayout()
        perf_row.setSpacing(15)

        self.perf_low = OptionCard("Low-spec / Fastest", "Reduces detector resolution and sampling frequency to lower CPU usage.")
        self.perf_balanced = OptionCard("Balanced", "A balanced middle ground for modern PCs and standard video processing.")
        self.perf_high = OptionCard("High Quality", "Checks nearly every frame for the most accurate detections. Slower.")
        self.perf_options = [self.perf_low, self.perf_balanced, self.perf_high]
        for opt in self.perf_options:
            opt.clicked.connect(self.select_performance_profile)
        initial_profile = CONFIG_TO_PERFORMANCE_PROFILE.get(cfg.performance_profile, "Balanced")
        for opt in self.perf_options:
            opt.set_selected(opt.value == initial_profile)

        perf_row.addWidget(self.perf_low)
        perf_row.addWidget(self.perf_balanced)
        perf_row.addWidget(self.perf_high)
        perf_layout.addLayout(perf_row)

        perf_layout.addSpacing(6)
        self.interval_slider = SettingSlider(
            "Face Detection Interval",
            "Run full detection every Nth frame. DeepSORT tracking fills in between.",
            min_val=1, max_val=30, init_val=cfg.detection_interval,
            format_fn=lambda v: f"Every {v} frames"
        )
        perf_layout.addWidget(self.interval_slider)

        self.jpeg_slider = SettingSlider(
            "JPEG Output Quality",
            "Compression quality for saved redacted frames.",
            min_val=1, max_val=100, init_val=cfg.jpeg_quality,
            format_fn=lambda v: f"{v}%"
        )
        perf_layout.addWidget(self.jpeg_slider)

        # Detection resolution scale — the single biggest lever for live-
        # stream lag on CPU, since YOLO inference cost scales with input
        # resolution. 100% = full resolution (most accurate, slowest).
        self.scale_slider = SettingSlider(
            "Detection Resolution",
            "Downscales frames before running YOLO26 detection, then scales boxes back up. "
            "Lower = faster, especially on CPU; full resolution stays accurate but is slower.",
            min_val=25, max_val=100, init_val=round(cfg.detection_scale * 100),
            format_fn=lambda v: f"{v}%"
        )
        perf_layout.addWidget(self.scale_slider)

        device_row = QHBoxLayout()
        device_lbl = QLabel("Inference Device")
        device_lbl.setStyleSheet("font-size: 13px;")
        self.device_combo = QComboBox()
        self.device_combo.addItems(["Auto (use GPU if available)", "CPU", "GPU (CUDA)"])
        device_index = {"auto": 0, "cpu": 1, "cuda": 2}.get(cfg.device, 0)
        self.device_combo.setCurrentIndex(device_index)
        device_row.addWidget(device_lbl)
        device_row.addStretch()
        device_row.addWidget(self.device_combo)
        perf_layout.addLayout(device_row)

        main_layout.addWidget(perf_card)

        # ---------------- 4. Detection Classes ----------------
        classes_card, classes_layout = group_card(
            "Detection Classes",
            "Choose which privacy classes PrivARcy should detect. Unchecked classes are left untouched."
        )
        classes_grid = QGridLayout()
        classes_grid.setHorizontalSpacing(30)
        classes_grid.setVerticalSpacing(10)
        self.detection_checkboxes = {}
        for i, cls in enumerate(DETECTION_CLASSES):
            cb = QCheckBox(f"  {cls}")
            cb.setChecked(DETECTION_CLASS_TO_CONFIG[cls] in cfg.enabled_classes)
            cb.setCursor(Qt.PointingHandCursor)
            row, col = divmod(i, 3)
            classes_grid.addWidget(cb, row, col)
            self.detection_checkboxes[cls] = cb
        classes_layout.addLayout(classes_grid)
        main_layout.addWidget(classes_card)

        # ---------------- 5. System Diagnostics ----------------
        # Every model component (YOLO26 detector, TrOCR, face_recognition)
        # is designed to fail silently during processing — a broken/missing
        # model should never crash a job — but that means a genuinely empty
        # video and "the detector never loaded" look identical from the
        # Review/Results pages alone. This panel lets you check *before*
        # running a whole video instead of finding out after.
        diag_card, diag_layout = group_card(
            "System Diagnostics",
            "Checks whether the detection/OCR/face-recognition models actually "
            "load on this machine. A model that fails to load produces zero "
            "detections for every video, silently — this is how to tell why."
        )
        self._diag_rows = {}
        for key, label in (("detector", "YOLO26 Detector"), ("ocr", "TrOCR"), ("face_recognition", "Face Recognition")):
            row = QHBoxLayout()
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("font-size: 13px;")
            status_lbl = QLabel("Not checked yet")
            status_lbl.setStyleSheet("font-size: 13px; color: #9AA0A6;")
            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(status_lbl)
            diag_layout.addLayout(row)
            self._diag_rows[key] = status_lbl

        diag_btn = QPushButton("Run Diagnostics")
        diag_btn.setObjectName("SecondaryButton")
        diag_btn.setFixedHeight(38)
        diag_btn.setCursor(Qt.PointingHandCursor)
        diag_btn.clicked.connect(self.run_diagnostics)
        diag_layout.addWidget(diag_btn)
        main_layout.addWidget(diag_card)

        # ---------------- 6. Correction Feedback ----------------
        # Every reviewer decision (Confirm/Reject) on a flagged detection
        # is logged locally. This turns that accumulated feedback into
        # updated confidence weights for the rule-based sensitivity
        # classifier's patterns — a pattern reviewers keep rejecting
        # contributes less over time. This never touches YOLO26 or TrOCR;
        # it only adjusts the classifier's own pattern weights.
        correction_card, correction_layout = group_card(
            "Correction Feedback",
            "Improves the sensitivity classifier from accumulated reviewer "
            "decisions, without retraining any model. Run this occasionally "
            "as the Correction Log builds up — not after every single review."
        )
        self._correction_status_lbl = QLabel("Not checked yet")
        self._correction_status_lbl.setStyleSheet("font-size: 13px; color: #9AA0A6;")
        self._correction_status_lbl.setWordWrap(True)
        correction_layout.addWidget(self._correction_status_lbl)

        refine_btn = QPushButton("Refine Classifier from Corrections")
        refine_btn.setObjectName("SecondaryButton")
        refine_btn.setFixedHeight(38)
        refine_btn.setCursor(Qt.PointingHandCursor)
        refine_btn.clicked.connect(self.refine_classifier)
        correction_layout.addWidget(refine_btn)
        main_layout.addWidget(correction_card)

        # ---------------- Save ----------------
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setFixedHeight(48)
        save_btn.clicked.connect(self.save_settings)
        main_layout.addWidget(save_btn)

        self.banner = NotificationBanner()
        main_layout.addWidget(self.banner)

        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

    def select_redaction_style(self, chosen):
        for opt in self.redaction_style_options:
            opt.set_selected(opt is chosen)

    def select_performance_profile(self, chosen):
        for opt in self.perf_options:
            opt.set_selected(opt is chosen)
        preset = PERFORMANCE_PRESETS.get(chosen.value)
        if preset:
            self.interval_slider.setValue(preset["interval"])
            self.jpeg_slider.setValue(preset["jpeg"])

    def run_diagnostics(self):
        """Attempts to load each model component right now and reports
        whether it actually works — see BackendService.diagnostics()."""
        for status_lbl in self._diag_rows.values():
            status_lbl.setText("Checking…")
            status_lbl.setStyleSheet("font-size: 13px; color: #9AA0A6;")
        QApplication.processEvents()  # let the "Checking…" state paint before the (blocking) load attempts

        results = self._backend.diagnostics()
        any_failed = False
        for key, status_lbl in self._diag_rows.items():
            info = results.get(key, {})
            if info.get("loaded"):
                device_note = f" ({info['device']})" if info.get("device") else ""
                status_lbl.setText(f"✓ Working{device_note}")
                status_lbl.setStyleSheet("font-size: 13px; color: #34D399; font-weight: 600;")
            else:
                any_failed = True
                error = (info.get("error") or "")[:80]
                status_lbl.setText(f"✗ Failed{': ' + error if error else ''}")
                status_lbl.setStyleSheet("font-size: 13px; color: #F87171; font-weight: 600;")
                status_lbl.setToolTip(info.get("error") or "")

        if any_failed:
            self.banner.show_message(
                "One or more models failed to load — processing will still run, but "
                "affected detections will be silently skipped. See backend/logs/privarcy.log "
                "for the full error.", "warning"
            )
        else:
            self.banner.show_message("All models loaded successfully.", "success")

    def refine_classifier(self):
        """Recompute the rule-based classifier's pattern weights from the
        Correction Log — see BackendService.refine_classifier()."""
        total_logged = self._backend.correction_log.total_logged()
        if total_logged == 0:
            self._correction_status_lbl.setText(
                "No corrections logged yet — Confirm/Reject some flagged detections in "
                "Review first, then come back here."
            )
            self._correction_status_lbl.setStyleSheet("font-size: 13px; color: #9AA0A6;")
            return

        result = self._backend.refine_classifier()
        updated = result["updated_patterns"]
        if not updated:
            self._correction_status_lbl.setText(
                f"{total_logged} correction(s) logged, but no pattern has enough decisions yet "
                f"to adjust (needs at least 5 per pattern)."
            )
            self._correction_status_lbl.setStyleSheet("font-size: 13px; color: #9AA0A6;")
        else:
            summary = ", ".join(f"{pattern} → {weight}" for pattern, weight in updated.items())
            self._correction_status_lbl.setText(f"Updated {len(updated)} pattern(s): {summary}")
            self._correction_status_lbl.setStyleSheet("font-size: 13px; color: #34D399; font-weight: 600;")
        self.banner.show_message(
            f"Classifier refined from {total_logged} logged correction(s).", "success"
        )

    def save_settings(self):
        selected_style = next((o.value for o in self.redaction_style_options if o.property("selected")), None)
        selected_profile = next((o.value for o in self.perf_options if o.property("selected")), None)
        enabled_classes = [DETECTION_CLASS_TO_CONFIG[name] for name, cb in self.detection_checkboxes.items() if cb.isChecked()]

        # Persist to the shared AppConfig (data/settings.json) so every
        # other page — Process, Live — picks up these values on its next
        # run, instead of only updating a page-local dict nothing reads.
        self._backend.config.apply_performance_profile(
            PERFORMANCE_PROFILE_TO_CONFIG.get(selected_profile, self._backend.config.performance_profile)
        )
        self._backend.update_settings(
            confidence_threshold=self.t_high_slider.value() / 100.0,
            low_threshold=self.t_low_slider.value() / 100.0,
            temporal_smoothing=self.smoothing_slider.value(),
            iou_threshold=self.iou_slider.value() / 100.0,
            track_termination=self.track_term_slider.value(),
            redaction_method=REDACTION_STYLE_TO_CONFIG.get(selected_style, self._backend.config.redaction_method),
            detection_interval=self.interval_slider.value(),
            jpeg_quality=self.jpeg_slider.value(),
            enabled_classes=enabled_classes,
            detection_scale=self.scale_slider.value() / 100.0,
            device=["auto", "cpu", "cuda"][self.device_combo.currentIndex()],
        )

        # A live stream's detector/decision-engine/redactor snapshot config
        # values at construction — restart it so these changes actually
        # take effect immediately instead of silently only applying to the
        # *next* stream or processing job.
        if self._backend.restart_live_if_active():
            self.banner.show_message(
                "Settings saved — the active live stream was restarted to apply them.", "success"
            )
        else:
            self.banner.show_message("Settings saved successfully.", "success")

    def retheme(self):
        retheme_widget_tree(self)
