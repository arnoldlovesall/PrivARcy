# Process.py
import os, sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QProgressBar, QPushButton, QFileDialog, QCheckBox,
                             QRadioButton, QButtonGroup, QSlider, QStackedWidget)
from PyQt5.QtCore import Qt
import styles
from components import (create_icon, retheme_widget_tree, create_scrollable_container,
                        NotificationBanner, LoadingState, ErrorState)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from qt_worker import QtProcessingWorker


class WheelSafeSlider(QSlider):
    def wheelEvent(self, event):
        event.ignore()


class MetricCard(QFrame):
    """Compact metric card used in the processing dashboard."""
    def __init__(self, icon, title, value, unit=""):
        super().__init__()
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(create_icon(icon, styles.ACCENT_TEAL, 22).pixmap(22, 22))
        self.icon_lbl._retheme_icon = lambda: self.icon_lbl.setPixmap(
            create_icon(icon, styles.CURRENT_COLORS['ACCENT_TEAL'], 22).pixmap(22, 22))
        layout.addWidget(self.icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title_lbl = QLabel(title)
        styles.themed(title_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 500;")
        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(self.value_lbl)
        layout.addLayout(text_layout)

    def set_value(self, v):
        self.value_lbl.setText(str(v))


class ProcessPage(QWidget):
    """Polished video processing workspace with logical sections.

    Frontend-only. All processing methods (set_progress, set_processing_state, etc.)
    are provided as clean APIs for the future backend to call.
    """

    PENDING, ACTIVE, DONE = "pending", "active", "done"
    STATES = ("idle", "processing", "completed", "error")

    def __init__(self, navigate_callback, backend):
        super().__init__()
        self.navigate = navigate_callback
        self.frames = 0
        self.detected = 0
        self.flagged = 0
        self.stage_index = 0
        self.elapsed_seconds = 0
        self._processing_state = "idle"
        self._selected_file = None
        # Shared with every other page via MainWindow, instead of each page
        # opening its own BackendService — otherwise Settings changes,
        # registered faces, and the review queue would silently diverge
        # between pages.
        self._backend = backend
        self._worker = None
        self.on_processing_complete = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(20)

        # Header Section
        header_section = QVBoxLayout()
        header_section.setSpacing(4)
        title = QLabel("Process Video")
        title.setObjectName("PageTitle")
        desc = QLabel("Configure detection, run privacy redaction, and review results. All processing is local.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        header_section.addWidget(title)
        header_section.addWidget(desc)
        main_layout.addLayout(header_section)

        self.banner = NotificationBanner()
        main_layout.addWidget(self.banner)

        # ---- INPUT SECTION ----
        input_card, input_layout = self._create_group_card("Input", "Select a video file to begin.")
        self.input_inner = QVBoxLayout()
        self.input_inner.setSpacing(12)

        self.file_info_lbl = QLabel("No video selected")
        self.file_info_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.input_inner.addWidget(self.file_info_lbl)

        self.file_meta_lbl = QLabel("Choose a video file to see its details here.")
        styles.themed(self.file_meta_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        self.file_meta_lbl.setWordWrap(True)
        self.input_inner.addWidget(self.file_meta_lbl)

        select_btn = QPushButton("  Select Video")
        select_btn.setObjectName("PrimaryButton")
        select_btn.setIcon(create_icon("video", "#FFFFFF", 18))
        select_btn.setFixedHeight(44)
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.clicked.connect(self.select_video)
        self.input_inner.addWidget(select_btn)
        self.input_inner.addStretch()

        input_layout.addLayout(self.input_inner)
        main_layout.addWidget(input_card)

        # ---- DETECTION SETTINGS ----
        settings_card, settings_layout = self._create_group_card(
            "Detection Settings", "Choose what to detect and how strictly."
        )

        # Detection type checkboxes
        det_row = QHBoxLayout()
        det_row.setSpacing(24)
        self.det_checkboxes = {}
        self._class_map = {
            "Faces": "faces",
            "IDs": "ids",
            "Credentials": "credentials",
            "Documents": "documents",
            "Screens": "screens",
            "License Plates": "license plates",
        }
        for label in self._class_map:
            cb = QCheckBox(f"  {label}")
            enabled = self._backend.config.enabled_classes if self._backend else None
            cb.setChecked(True if enabled is None else self._class_map[label] in enabled)
            cb.setCursor(Qt.PointingHandCursor)
            det_row.addWidget(cb)
            self.det_checkboxes[label] = cb
        det_row.addStretch()
        settings_layout.addLayout(det_row)

        # Confidence threshold slider
        conf_row = QHBoxLayout()
        conf_lbl = QLabel("Confidence Threshold")
        conf_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        conf_row.addWidget(conf_lbl)
        conf_row.addStretch()
        self.conf_value_lbl = QLabel("0.75")
        styles.themed(self.conf_value_lbl, lambda: f"color: {styles.ACCENT_TEAL}; font-weight: bold; font-size: 13px;")
        conf_row.addWidget(self.conf_value_lbl)
        settings_layout.addLayout(conf_row)

        self.conf_slider = WheelSafeSlider(Qt.Horizontal)
        self.conf_slider.setRange(0, 100)
        self.conf_slider.setValue(round(self._backend.config.confidence_threshold * 100))
        self.conf_value_lbl.setText(f"{self._backend.config.confidence_threshold:.2f}")
        self.conf_slider.valueChanged.connect(self._on_conf_change)
        settings_layout.addWidget(self.conf_slider)

        # Redaction method radios
        redact_lbl = QLabel("Redaction Method")
        redact_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        settings_layout.addWidget(redact_lbl)

        redact_row = QHBoxLayout()
        redact_row.setSpacing(16)
        self.redact_group = QButtonGroup(self)
        self._redaction_methods = ["Blur", "Pixelate", "Solid Mask"]
        self._redaction_to_config = {"Blur": "blur", "Pixelate": "pixelate", "Solid Mask": "solid mask"}
        self._redaction_method = self._redaction_methods[0]
        for i, name in enumerate(self._redaction_methods):
            rb = QRadioButton(name)
            rb.setCursor(Qt.PointingHandCursor)
            if i == 0:
                rb.setChecked(True)
            self.redact_group.addButton(rb, i)
            redact_row.addWidget(rb)
        redact_row.addStretch()
        self.redact_group.buttonClicked[int].connect(self._on_redaction_method_change)
        settings_layout.addLayout(redact_row)

        main_layout.addWidget(settings_card)

        # ---- PROCESSING SECTION ----
        self.processing_card, proc_layout = self._create_group_card(
            "Processing", "Live progress for the active processing job."
        )

        # State stack: idle -> loading -> error -> active processing -> complete
        self.processing_stack = QStackedWidget()
        proc_layout.addWidget(self.processing_stack)

        # Page 0: Idle state
        self.idle_widget = QWidget()
        idle_layout = QVBoxLayout(self.idle_widget)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setSpacing(12)

        self.state_lbl = QLabel("Ready to process")
        self.state_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        idle_layout.addWidget(self.state_lbl)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setObjectName("MainProgress")
        idle_layout.addWidget(self.progress_bar)

        # Metric grid
        metric_grid = QHBoxLayout()
        metric_grid.setSpacing(14)
        self.m_frames = MetricCard("frame", "Frame", "0 / 0", "")
        self.m_fps = MetricCard("speed", "FPS", "—", "")
        self.m_detected = MetricCard("detect", "Detections", "0", "")
        self.m_flagged = MetricCard("flag", "Flagged", "0", "")
        self.m_eta = MetricCard("speed", "ETA", "—", "")

        metric_grid.addWidget(self.m_frames)
        metric_grid.addWidget(self.m_fps)
        metric_grid.addWidget(self.m_detected)
        metric_grid.addWidget(self.m_flagged)
        metric_grid.addWidget(self.m_eta)
        idle_layout.addLayout(metric_grid)

        # Action buttons
        action_row = QHBoxLayout()
        self.start_btn = QPushButton("  Start Processing")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setIcon(create_icon("play", "#FFFFFF", 16))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start_clicked)
        action_row.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("  Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.setIcon(create_icon("close", styles.ACCENT_RED, 16))
        self.cancel_btn.setFixedHeight(44)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        action_row.addWidget(self.cancel_btn)
        action_row.addStretch()

        idle_layout.addLayout(action_row)

        # Page 1: Loading state (when starting)
        self.loading_state = LoadingState("Initializing processing pipeline...")

        # Page 2: Error state
        self.error_state = ErrorState(
            title="Processing Error",
            description="An error occurred during video processing.",
            retry_text="Retry",
            on_retry=self._on_start_clicked
        )

        # Page 3: Active processing (same as idle but with different state label)
        self.active_widget = QWidget()
        active_layout = QVBoxLayout(self.active_widget)
        active_layout.setContentsMargins(0, 0, 0, 0)
        active_layout.setSpacing(12)

        self.active_state_lbl = QLabel("Processing video...")
        self.active_state_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        active_layout.addWidget(self.active_state_lbl)

        self.active_progress_bar = QProgressBar()
        self.active_progress_bar.setRange(0, 100)
        self.active_progress_bar.setValue(0)
        self.active_progress_bar.setFormat("%p%")
        self.active_progress_bar.setObjectName("MainProgress")
        active_layout.addWidget(self.active_progress_bar)

        # Active metric grid
        active_metric_grid = QHBoxLayout()
        active_metric_grid.setSpacing(14)
        self.active_m_frames = MetricCard("frame", "Frame", "0 / 0", "")
        self.active_m_fps = MetricCard("speed", "FPS", "—", "")
        self.active_m_detected = MetricCard("detect", "Detections", "0", "")
        self.active_m_flagged = MetricCard("flag", "Flagged", "0", "")
        self.active_m_eta = MetricCard("speed", "ETA", "—", "")

        active_metric_grid.addWidget(self.active_m_frames)
        active_metric_grid.addWidget(self.active_m_fps)
        active_metric_grid.addWidget(self.active_m_detected)
        active_metric_grid.addWidget(self.active_m_flagged)
        active_metric_grid.addWidget(self.active_m_eta)
        active_layout.addLayout(active_metric_grid)

        active_action_row = QHBoxLayout()
        self.active_cancel_btn = QPushButton("  Cancel")
        self.active_cancel_btn.setObjectName("SecondaryButton")
        self.active_cancel_btn.setIcon(create_icon("close", styles.ACCENT_RED, 16))
        self.active_cancel_btn.setFixedHeight(44)
        self.active_cancel_btn.setCursor(Qt.PointingHandCursor)
        self.active_cancel_btn.clicked.connect(self._on_cancel_clicked)
        active_action_row.addWidget(self.active_cancel_btn)
        active_action_row.addStretch()
        active_layout.addLayout(active_action_row)

        self.processing_stack.addWidget(self.idle_widget)
        self.processing_stack.addWidget(self.loading_state)
        self.processing_stack.addWidget(self.error_state)
        self.processing_stack.addWidget(self.active_widget)

        main_layout.addWidget(self.processing_card)

        # ---- COMPLETED STATE (initially hidden) ----
        self.complete_card, complete_layout = self._create_group_card(
            "Processing Complete", ""
        )
        self.complete_card.hide()

        self.complete_msg_lbl = QLabel("Video processed successfully.")
        self.complete_msg_lbl.setStyleSheet("font-size: 14px;")
        complete_layout.addWidget(self.complete_msg_lbl)

        self.complete_stats = QHBoxLayout()
        self.complete_stats.setSpacing(14)
        self.cs_frames = MetricCard("frame", "Frames Processed", "0", "")
        self.cs_time = MetricCard("speed", "Processing Time", "00:00", "")
        self.cs_detections = MetricCard("detect", "Detections", "0", "")
        self.cs_redactions = MetricCard("shield", "Redactions", "0", "")
        self.complete_stats.addWidget(self.cs_frames)
        self.complete_stats.addWidget(self.cs_time)
        self.complete_stats.addWidget(self.cs_detections)
        self.complete_stats.addWidget(self.cs_redactions)
        complete_layout.addLayout(self.complete_stats)

        complete_actions = QHBoxLayout()
        self.open_output_btn = QPushButton("  Open Output")
        self.open_output_btn.setObjectName("PrimaryButton")
        self.open_output_btn.setIcon(create_icon("play", "#FFFFFF", 16))
        self.open_output_btn.setFixedHeight(40)
        self.open_output_btn.setCursor(Qt.PointingHandCursor)
        self.open_output_btn.clicked.connect(lambda: self.navigate("Results"))
        complete_actions.addWidget(self.open_output_btn)

        self.review_btn = QPushButton("  Review Results")
        self.review_btn.setObjectName("SecondaryButton")
        self.review_btn.setIcon(create_icon("review", styles.ACCENT_TEAL, 16))
        self.review_btn.setFixedHeight(40)
        self.review_btn.setCursor(Qt.PointingHandCursor)
        self.review_btn.clicked.connect(lambda: self.navigate("Review"))
        complete_actions.addWidget(self.review_btn)
        complete_actions.addStretch()
        complete_layout.addLayout(complete_actions)

        main_layout.addWidget(self.complete_card)

        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

    def _create_group_card(self, title, hint):
        """Create a titled card container."""
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title_lbl)

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet("font-size: 12px;")
            styles.themed(hint_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
            hint_lbl.setWordWrap(True)
            layout.addWidget(hint_lbl)

        return card, layout

    def _on_conf_change(self, val):
        self.conf_value_lbl.setText(f"{val/100:.2f}")

    def _on_redaction_method_change(self, index):
        """Update the configured redaction method immediately on selection."""
        self._redaction_method = self._redaction_methods[index]

    def get_redaction_method(self):
        """Public API: returns the currently selected redaction method
        ('Blur', 'Pixelate', or 'Solid Mask'), which the future backend
        should use when processing the video."""
        return self._redaction_method

    def select_video(self):
        """Open a file picker for video selection."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if path:
            self._selected_file = path
            self.file_info_lbl.setText(os.path.basename(path))
            self.file_meta_lbl.setText(
                f"Path: {path}\nSize: {os.path.getsize(path) / (1024*1024):.1f} MB"
            )

    def _on_start_clicked(self):
        """Handle the Start Processing button: run the real YOLO26 + TrOCR
        + rule-based classification + confidence-gated review pipeline on
        a background QThread and drive this page's progress UI from its
        signals."""
        if not self._selected_file:
            self.banner.show_message(
                "Select a video file before starting.", kind="warning"
            )
            return

        # Apply only the two controls this page owns (confidence + redaction
        # method) on top of the shared config, instead of replacing it —
        # otherwise every other setting configured on the Settings page
        # (low threshold, model paths, enabled classes, performance
        # profile, ...) would silently reset to defaults on every run.
        enabled = [
            self._class_map[label]
            for label, cb in self.det_checkboxes.items()
            if cb.isChecked()
        ]
        self._backend.config.update(
            confidence_threshold=self.conf_slider.value() / 100,
            redaction_method=self._redaction_to_config.get(self._redaction_method, "blur"),
            enabled_classes=enabled or set(self._class_map.values()),
        )

        self._worker = QtProcessingWorker(
            self._selected_file,
            config=self._backend.config,
            source_name=os.path.basename(self._selected_file),
            review_store=self._backend.review_store,
            parent=self,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.completed.connect(self._on_worker_completed)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.cancelled.connect(lambda: self.banner.show_message("Processing cancelled.", "info"))
        self.set_processing_state("processing")
        self._worker.start(            )

    def set_video(self, path):
        """Pre-fill the file picker from Home's Browse Files selection."""
        if not path:
            return
        self._selected_file = path
        self.file_info_lbl.setText(os.path.basename(path))
        try:
            size = os.path.getsize(path) / (1024 * 1024)
        except OSError:
            size = 0
        self.file_meta_lbl.setText(f"Path: {path}\nSize: {size:.1f} MB")

    def _on_cancel_clicked(self):
        """Return to the idle state."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        self._processing_state = "idle"
        self.processing_stack.setCurrentIndex(0)  # Idle state
        self.state_lbl.setText("Cancelled")
        self.state_lbl.setStyleSheet("color: {}; font-size: 15px; font-weight: 700;".format(styles.ACCENT_RED))
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_worker_progress(self, current, total, detected, redactions):
        self.set_frame_progress(current, total)
        self.set_progress(100 * current / total if total else 0)
        self.set_detected(detected)
        self.set_flagged(max(0, detected - redactions))

    def _on_worker_completed(self, result):
        self.set_detected(len(result.detections))
        self.set_flagged(sum(d.get("status") == "pending" for d in result.detections))
        self._on_processing_complete()

        if not result.detections:
            # A processed video with zero detections is either genuinely
            # empty of privacy-sensitive content, or the detector/OCR
            # model never loaded in the first place — those look
            # identical from here otherwise, since a failed model load
            # never raises (see YoloDetector/OCRService). Distinguish
            # them for the user instead of just saying "Finished."
            diagnostics = self._backend.diagnostics()
            broken = [
                name for name, info in diagnostics.items()
                if not info["loaded"]
            ]
            if broken:
                self.banner.show_message(
                    f"Finished, but 0 detections — {', '.join(broken)} failed to load "
                    f"(see Settings > System Diagnostics for details), so nothing could "
                    f"be found regardless of video content.",
                    "warning",
                )
            else:
                self.banner.show_message(
                    f"Finished. Output: {result.output_path} — no privacy-sensitive "
                    f"regions were detected in this video.",
                    "info",
                )
        else:
            self.banner.show_message(f"Finished. Output: {result.output_path}", "success")

        if callable(self.on_processing_complete):
            self.on_processing_complete(result)

    def _on_worker_failed(self, message):
        self.banner.show_message(message, "error")
        self.set_processing_state("error")

    def _on_processing_complete(self):
        """Populate and reveal the completion card.

        Called only via set_processing_state('completed') — never triggered
        automatically by a fake timer. The future backend calls this path
        once real processing has actually finished.
        """
        self._processing_state = "completed"
        self.processing_stack.setCurrentIndex(0)  # Back to idle
        self.state_lbl.setText("✓ Processing complete")
        self.state_lbl.setStyleSheet("color: {}; font-size: 15px; font-weight: 700;".format(styles.ACCENT_TEAL))
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        # Populate completion card from whatever the backend last reported
        # via set_frame_progress/set_detected/etc. (falls back to 0s if the
        # backend hasn't supplied real numbers yet).
        self.cs_frames.set_value(f"{self.frames:,}")
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        self.cs_time.set_value(f"{mins:02d}:{secs:02d}")
        self.cs_detections.set_value(str(self.detected))
        self.cs_redactions.set_value(str(max(0, self.detected - 2)))
        self.complete_card.show()

    # === PUBLIC API FOR FUTURE BACKEND ===
    def set_progress(self, percent):
        """Update progress bar (0-100)."""
        self.progress_bar.setValue(int(percent))
        self.active_progress_bar.setValue(int(percent))

    def set_frame_progress(self, current, total):
        """Update frame counter."""
        self.frames = current
        self.m_frames.set_value(f"{current:,} / {total:,}")
        self.active_m_frames.set_value(f"{current:,} / {total:,}")

    def set_processing_fps(self, fps):
        """Update processing FPS metric."""
        self.m_fps.set_value(f"{fps:.1f}")
        self.active_m_fps.set_value(f"{fps:.1f}")

    def set_eta(self, seconds):
        """Update ETA in seconds."""
        self.m_eta.set_value(f"00:{int(seconds):02d}")
        self.active_m_eta.set_value(f"00:{int(seconds):02d}")

    def set_processing_state(self, state):
        """Set the processing state. Use 'idle', 'loading', 'processing', 'completed', 'error'."""
        self._processing_state = state
        if state == "idle":
            self.processing_stack.setCurrentIndex(0)
            self.state_lbl.setText("Ready to process")
            self.state_lbl.setStyleSheet("")
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
        elif state == "loading":
            self.processing_stack.setCurrentIndex(1)  # Loading state
            self.start_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
        elif state == "processing":
            # Backend-driven transition: just switch to the active layout.
            # Real numbers arrive via set_progress/set_frame_progress/etc.
            self._processing_state = "processing"
            self.start_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.complete_card.hide()
            self.processing_stack.setCurrentIndex(3)
            self.active_state_lbl.setText("Processing video...")
            self.active_state_lbl.setStyleSheet(
                "color: {}; font-size: 15px; font-weight: 700;".format(styles.ACCENT_TEAL)
            )
        elif state == "completed":
            self._on_processing_complete()
        elif state == "error":
            self.processing_stack.setCurrentIndex(2)  # Error state
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)

    def set_detected(self, count):
        """Update detected count."""
        self.detected = count
        self.m_detected.set_value(str(count))
        self.active_m_detected.set_value(str(count))

    def set_flagged(self, count):
        """Update flagged count."""
        self.flagged = count
        self.m_flagged.set_value(str(count))
        self.active_m_flagged.set_value(str(count))

    def retheme(self):
        retheme_widget_tree(self)
        # Refresh the reusable state components
        if hasattr(self, 'loading_state'):
            self.loading_state.retheme()
        if hasattr(self, 'error_state'):
            self.error_state.retheme()

    def reset(self):
        """Public API: clear the current session so a new video can be
        processed from a clean slate (used by Results' 'Process Another
        Video' action)."""
        self._selected_file = None
        self.frames = 0
        self.detected = 0
        self.flagged = 0
        self.elapsed_seconds = 0
        self.file_info_lbl.setText("No video selected")
        self.file_meta_lbl.setText("Choose a video file to see its details here.")
        self.complete_card.hide()
        self.banner.hide()
        self.set_processing_state("idle")
        self.set_progress(0)
        self.set_frame_progress(0, 0)
        self.set_processing_fps(0)
        self.set_eta(0)
        self.set_detected(0)
        self.set_flagged(0)
