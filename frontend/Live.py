# Live.py
import os
import sys

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QScrollArea, QSizePolicy, QShortcut,
                             QComboBox, QMessageBox, QSlider)
from PyQt5.QtGui import QKeySequence, QImage, QPixmap
from PyQt5.QtCore import Qt, QTimer, QDateTime, pyqtSignal
import styles
from components import create_icon, retheme_widget_tree, create_scrollable_container, EmptyState

try:
    import cv2
except ImportError:  # pragma: no cover - surfaced to the user via the UI instead
    cv2 = None

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Try to get Windows camera device names in DirectShow enumeration order
try:
    from pygrabber.dshow_graph import FilterGraph
    PYGRABBER_AVAILABLE = True
except ImportError:
    PYGRABBER_AVAILABLE = False

# ============================================================================
# NOTICE
# ----------------------------------------------------------------------------
# This page owns local camera selection/naming and preview display. Actual
# capture and the real per-frame pipeline (YOLO26 detection -> TrOCR -> rule-
# based classification -> confidence-gated decision -> redaction) run on
# LiveSession's own background thread (backend/src/live/session.py), started
# via BackendService.start_live()/stop_live(). This page's frame timer only
# polls the resulting JPEG frames/stats/audit log — it never runs the
# pipeline itself, which is what keeps the GUI thread responsive.
# ============================================================================

# How many device indices to probe when looking for connected cameras.
# OpenCV has no cross-platform "list cameras" call, so probing a small range
# of indices is the standard approach.
MAX_CAMERAS_TO_PROBE = 8

# Requested capture modes offered in the resolution dropdown. Actual
# granted resolution/fps depends on the camera/driver — LiveSession reads
# it back after opening rather than assuming these were honored.
RESOLUTION_PRESETS = {
    "640×480": (640, 480, 30),
    "1280×720 (HD)": (1280, 720, 30),
    "1920×1080 (Full HD) @ 60fps": (1920, 1080, 60),
    "3840×2160 (4K) @ 30fps": (3840, 2160, 30),
}


class ScrollableSlider(QSlider):
    """Slider that only changes through deliberate pointer or keyboard input."""
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def wheelEvent(self, event):
        event.ignore()


def _get_windows_camera_names():
    """Get the actual camera device names, in the same order OpenCV's
    CAP_DSHOW enumerates them.

    Previously this read `Control Panel\\Device Managers\\{GUID}` from the
    registry — that key doesn't reliably list capture devices at all (it's
    not where DirectShow friendly names live), so it always came back
    empty and every camera fell through to a "DSHOW (device N)"-style
    fallback name that used the *backend* API name, not the device name.

    `pygrabber` enumerates DirectShow's actual filter graph, so its index
    order matches what `cv2.VideoCapture(index, cv2.CAP_DSHOW)` opens.
    """
    if sys.platform != "win32" or not PYGRABBER_AVAILABLE:
        return {}
    try:
        devices = FilterGraph().get_input_devices()
        return {i: name for i, name in enumerate(devices)}
    except Exception:
        return {}


class _CameraControlCard(QFrame):
    """Camera control panel with flip, size, and quality settings."""
    
    flipClicked = pyqtSignal()
    sizeChanged = pyqtSignal(int)
    qualityChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        
        # Title
        title_lbl = QLabel("Camera Controls")
        title_lbl.setObjectName("GroupTitle")
        layout.addWidget(title_lbl)
        
        # Controls row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)
        
        # Flip button
        self.flip_btn = QPushButton("  Flip Camera")
        self.flip_btn.setObjectName("SecondaryButton")
        self.flip_btn.setIcon(create_icon("flip", styles.ACCENT_TEAL, 14))
        self.flip_btn.setFixedHeight(36)
        self.flip_btn.setCursor(Qt.PointingHandCursor)
        self.flip_btn.clicked.connect(self.flipClicked.emit)
        controls_row.addWidget(self.flip_btn)
        
        # Size adjustment
        size_label = QLabel("Preview Size:")
        size_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        controls_row.addWidget(size_label)
        
        self.size_slider = ScrollableSlider(Qt.Horizontal)
        self.size_slider.setRange(50, 150)
        self.size_slider.setValue(100)
        self.size_slider.setFixedWidth(120)
        self.size_slider.setToolTip("Adjust camera preview size")
        controls_row.addWidget(self.size_slider)
        
        self.size_value_lbl = QLabel("100%")
        self.size_value_lbl.setStyleSheet("font-size: 12px;")
        self.size_value_lbl.setFixedWidth(40)
        self.size_slider.valueChanged.connect(lambda v: self.size_value_lbl.setText(f"{v}%"))
        self.size_slider.valueChanged.connect(self.sizeChanged.emit)
        controls_row.addWidget(self.size_value_lbl)
        
        controls_row.addSpacing(20)
        
        # Quality adjustment
        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        controls_row.addWidget(quality_label)
        
        self.quality_slider = ScrollableSlider(Qt.Horizontal)
        self.quality_slider.setRange(30, 100)
        self.quality_slider.setValue(80)
        self.quality_slider.setFixedWidth(120)
        self.quality_slider.setToolTip("Adjust camera frame quality")
        controls_row.addWidget(self.quality_slider)
        
        self.quality_value_lbl = QLabel("80%")
        self.quality_value_lbl.setStyleSheet("font-size: 12px;")
        self.quality_value_lbl.setFixedWidth(40)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_value_lbl.setText(f"{v}%"))
        self.quality_slider.valueChanged.connect(self.qualityChanged.emit)
        controls_row.addWidget(self.quality_value_lbl)
        
        controls_row.addStretch()
        layout.addLayout(controls_row)


class _StatCard(QFrame):
    """Compact stat tile used in the live-stats row."""
    def __init__(self, label, initial="0", icon_name=None):
        super().__init__()
        self.setObjectName("LiveStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        if icon_name:
            icon_lbl = QLabel()
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 18).pixmap(18, 18))
            icon_lbl._retheme_icon = lambda: icon_lbl.setPixmap(
                create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 18).pixmap(18, 18))
            layout.addWidget(icon_lbl)

        self._value_lbl = QLabel(initial)
        self._value_lbl.setObjectName("LiveStatValue")
        self._value_lbl.setAlignment(Qt.AlignCenter)

        label_lbl = QLabel(label.upper())
        label_lbl.setObjectName("LiveStatLabel")
        label_lbl.setAlignment(Qt.AlignCenter)
        label_lbl.setWordWrap(True)

        layout.addWidget(self._value_lbl)
        layout.addWidget(label_lbl)

    def set_value(self, v):
        self._value_lbl.setText(str(v))


class _AuditEntry(QFrame):
    """One row in the Audit Log."""
    def __init__(self, index, ts, desc, kind="face"):
        super().__init__()
        self.setObjectName("AuditLogEntry")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon(kind, styles.ACCENT_RED, 16).pixmap(16, 16))
        row.addWidget(icon_lbl)

        idx_lbl = QLabel(f"#{index:04d}")
        idx_lbl.setStyleSheet("font-size: 11px; font-weight: bold; min-width: 44px;")
        row.addWidget(idx_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("font-size: 12px;")
        row.addWidget(desc_lbl, 1)

        ts_lbl = QLabel(ts)
        styles.themed(ts_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 11px;")
        row.addWidget(ts_lbl)


class LivePage(QWidget):
    """Live Monitoring workspace.

    Owns local camera selection and raw preview (via OpenCV) so the user can
    pick and see a connected webcam right away. Detection/redaction results
    and live stats are never fabricated here — those are either left at zero
    or driven by the public API methods at the bottom of the class, which is
    what the future backend will call once it's wired in.
    """

    def __init__(self, backend):
        super().__init__()
        self.is_live = False
        # Shared with every other page via MainWindow — gives Live access to
        # the same config, face registry, and review queue as Process/Settings.
        self._backend = backend
        self._last_audit_count = 0
        self._last_seen_session = None  # detects Settings-triggered session restarts

        # Session counters — only ever change via the public API or the
        # honest elapsed-time clock below. Nothing here simulates detections.
        self._chunks = 0
        self._frames = 0
        self._auto_redacted = 0
        self._flagged = 0
        self._elapsed_secs = 0
        self._audit_entries = []

        # Camera state
        self._cameras = []          # list of dicts: {"index": int, "label": str}
        self._external_preview = False  # True once a backend calls set_preview_pixmap
        self._camera_flipped = False    # Track flip state
        self._current_frame = None      # Store current frame for flip effect
        self._requested_resolution = (1920, 1080, 60)  # matches _resolution_combo's default index
        
        # Get Windows camera names
        self._windows_camera_names = _get_windows_camera_names()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(20)

        # ── Header ───────────────────────────────────────────────────
        heading = QLabel("Live Monitoring")
        heading.setObjectName("PageTitle")
        desc = QLabel(
            "Preview and log real-time redaction from a connected camera source. "
            "Detection, OCR, and redaction run live via the shared PrivARcy pipeline."
        )
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        main_layout.addWidget(heading)
        main_layout.addWidget(desc)

        # ── Source Banner ────────────────────────────────────────────
        src_row = QHBoxLayout()
        cam_icon_lbl = QLabel()
        cam_icon_lbl.setPixmap(
            create_icon("webcam", styles.ACCENT_TEAL, 16).pixmap(16, 16)
        )
        cam_icon_lbl._retheme_icon = lambda: cam_icon_lbl.setPixmap(
            create_icon("webcam", styles.CURRENT_COLORS["ACCENT_TEAL"], 16).pixmap(16, 16)
        )
        src_row.addWidget(cam_icon_lbl)

        self._src_lbl = QLabel("Detecting cameras…")
        styles.themed(
            self._src_lbl,
            lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 600;"
        )
        src_row.addWidget(self._src_lbl)
        src_row.addStretch()

        self._camera_combo = QComboBox()
        self._camera_combo.setObjectName("CameraCombo")
        self._camera_combo.setMinimumWidth(280)
        self._camera_combo.setCursor(Qt.PointingHandCursor)
        self._camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        src_row.addWidget(self._camera_combo)

        # Requested capture resolution/frame rate. What the camera actually
        # grants (shown once live, in the source status line) can differ —
        # most webcams silently clamp modes they don't support, especially
        # 4K or 60fps.
        self._resolution_combo = QComboBox()
        self._resolution_combo.setObjectName("CameraCombo")
        self._resolution_combo.setMinimumWidth(170)
        self._resolution_combo.setCursor(Qt.PointingHandCursor)
        for label, (w, h, fps) in RESOLUTION_PRESETS.items():
            self._resolution_combo.addItem(label, (w, h, fps))
        self._resolution_combo.setCurrentIndex(2)  # 1920x1080 @ 60fps default
        self._resolution_combo.currentIndexChanged.connect(self._on_resolution_selected)
        src_row.addWidget(self._resolution_combo)

        self._refresh_btn = QPushButton("  Refresh")
        self._refresh_btn.setObjectName("SecondaryButton")
        self._refresh_btn.setIcon(create_icon("process", styles.ACCENT_TEAL, 14))
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.clicked.connect(self.refresh_cameras)
        src_row.addWidget(self._refresh_btn)

        main_layout.addLayout(src_row)

        # ── Preview Panel (Improved alignment and symmetry) ────────────────────────────────────────────
        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(20, 20, 20, 20)
        preview_layout.setSpacing(16)

        # Live Monitoring always uses a black background — regardless of the
        # app's Light/Dark theme — so detection overlays, bounding boxes, and
        # labels read clearly against the video feed. Not themed on purpose.
        self._preview_frame = QFrame()
        self._preview_frame.setStyleSheet(
            "background-color: #000000; border-radius: 12px;"
        )
        self._preview_frame.setMinimumHeight(360)
        self._preview_frame.setMaximumHeight(640)

        # Shows "off" until Start Live Stream opens the selected camera and
        # begins pushing frames in via set_preview_pixmap(); a future backend
        # can call set_preview_pixmap()/take_over_preview() to push its own
        # (e.g. redacted) frames here instead.
        self._webcam_lbl = QLabel("Live preview is off")
        self._webcam_lbl.setAlignment(Qt.AlignCenter)
        self._webcam_lbl.setStyleSheet(
            "background-color: #000000; border-radius: 12px; color: #E8EAED; font-weight: 600;"
        )
        self._webcam_lbl.setMinimumHeight(360)
        self._webcam_lbl.setMaximumHeight(640)
        self._webcam_lbl.setWordWrap(True)
        # Must actually fill the black frame — without an explicit Expanding
        # policy, a QLabel shrinks to its content's natural size (whatever
        # text/pixmap it currently holds), which is what caused the video
        # feed to render as a tiny thumbnail floating in a mostly-empty
        # black box instead of filling it.
        self._webcam_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        ph_layout = QVBoxLayout(self._preview_frame)
        ph_layout.setContentsMargins(0, 0, 0, 0)
        ph_layout.setSpacing(0)
        # No `alignment=` here — that flag tells the layout to center the
        # widget at its sizeHint() instead of stretching it to fill the
        # available space, which is what shrank the label down regardless
        # of the min/max height set above. self._webcam_lbl's own
        # setAlignment(Qt.AlignCenter) above already centers its *content*
        # (the pixmap/text) within whatever size it ends up filling.
        ph_layout.addWidget(self._webcam_lbl)
        preview_layout.addWidget(self._preview_frame)

        # Controls row (properly aligned)
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)
        self._status_lbl = QLabel("● Offline")
        styles.themed(self._status_lbl, self._status_style)
        ctrl_row.addWidget(self._status_lbl)
        ctrl_row.addStretch()

        self._toggle_btn = QPushButton("  Start Live Stream")
        self._toggle_btn.setObjectName("PrimaryButton")
        self._toggle_btn.setIcon(create_icon("play", "#FFFFFF", 16))
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setMinimumWidth(160)
        self._toggle_btn.clicked.connect(self.toggle_live)
        ctrl_row.addWidget(self._toggle_btn)

        preview_layout.addLayout(ctrl_row)
        main_layout.addWidget(preview_card)

        # ── Camera Controls Card (new feature) ──────────────────────────────
        self._camera_controls = _CameraControlCard()
        self._camera_controls.flipClicked.connect(self._flip_camera)
        self._camera_controls.sizeChanged.connect(self._set_preview_scale)
        self._camera_controls.qualityChanged.connect(self._set_preview_quality)
        main_layout.addWidget(self._camera_controls)

        # ── Real-time Stats Row ──────────────────────────────────────
        self._stat_chunks = _StatCard("Chunks Processed", "0", "detect")
        self._stat_frames = _StatCard("Frames", "0", "frame")
        self._stat_redacted = _StatCard("Auto-Redacted", "0", "blur")
        self._stat_flagged = _StatCard("Flagged", "0", "flag")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        for card in [self._stat_chunks, self._stat_frames,
                     self._stat_redacted, self._stat_flagged]:
            stats_row.addWidget(card, 1)
        main_layout.addLayout(stats_row)

        # ── Session Status Row ───────────────────────────────────────
        session_card = QFrame()
        session_card.setObjectName("Card")
        session_layout = QHBoxLayout(session_card)
        session_layout.setContentsMargins(20, 16, 20, 16)
        session_layout.setSpacing(30)

        sess_title = QLabel("Session Status")
        sess_title.setObjectName("GroupTitle")
        session_layout.addWidget(sess_title)
        session_layout.addStretch()

        self._elapsed_lbl = QLabel("Elapsed  00:00:00")
        self._elapsed_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        session_layout.addWidget(self._elapsed_lbl)

        sep = QLabel("·")
        styles.themed(sep, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 14px;")
        session_layout.addWidget(sep)

        self._chunk_len_lbl = QLabel("Chunk Length  30s")
        self._chunk_len_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        session_layout.addWidget(self._chunk_len_lbl)

        main_layout.addWidget(session_card)

        # ── Audit Log ────────────────────────────────────────────────
        audit_card = QFrame()
        audit_card.setObjectName("AuditLogCard")
        audit_outer = QVBoxLayout(audit_card)
        audit_outer.setContentsMargins(20, 16, 20, 16)
        audit_outer.setSpacing(10)

        audit_hdr = QHBoxLayout()
        audit_title = QLabel("Audit Log — Flagged & Auto-Redacted")
        audit_title.setObjectName("GroupTitle")
        audit_hdr.addWidget(audit_title)
        audit_hdr.addStretch()

        self._audit_count_lbl = QLabel("0 Events")
        self._audit_count_lbl.setObjectName("PillTeal")
        audit_hdr.addWidget(self._audit_count_lbl)
        audit_outer.addLayout(audit_hdr)

        # Scrollable log entries
        self._audit_scroll = QScrollArea()
        self._audit_scroll.setWidgetResizable(True)
        self._audit_scroll.setFrameShape(QFrame.NoFrame)
        self._audit_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._audit_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._audit_scroll.setMinimumHeight(140)
        self._audit_scroll.setMaximumHeight(220)

        self._audit_inner = QWidget()
        self._audit_inner_layout = QVBoxLayout(self._audit_inner)
        self._audit_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._audit_inner_layout.setSpacing(6)
        self._audit_inner_layout.setAlignment(Qt.AlignTop)

        # Empty state for audit log using reusable component
        self._audit_empty_state = EmptyState(
            title="No Events Yet",
            description="Start the live stream to begin monitoring flagged detections and auto-redactions.",
            icon_name="shield",
        )
        self._audit_inner_layout.addWidget(self._audit_empty_state)

        self._audit_scroll.setWidget(self._audit_inner)
        audit_outer.addWidget(self._audit_scroll)
        main_layout.addWidget(audit_card)

        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

        # The only timer on this page is an honest wall-clock for session
        # duration display — it never fabricates detection/redaction counts.
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(1000)
        self._session_timer.timeout.connect(self._tick_elapsed)

        # Space — Play/Pause. Scoped to this page (WidgetWithChildrenShortcut,
        # the default for a non-window parent) so it only fires while focus
        # is within the Live page, and never swallows spacebar presses meant
        # for text fields on other pages.
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_live)

        # Frame-grab timer for the local camera preview. Only ticks while
        # a camera-backed live session is active (see toggle_live).
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(33)  # ~30 FPS
        self._frame_timer.timeout.connect(self._grab_frame)

        # Populate the camera dropdown right away so the user can see what's
        # available before ever pressing "Start Live Stream".
        self.refresh_cameras()

    # ── Camera detection & selection ─────────────────────────────────

    def refresh_cameras(self):
        """(Re)detect connected cameras and repopulate the dropdown.

        Safe to call while a stream is live — if the currently-active camera
        disappears from the refreshed list, the stream is stopped.
        """
        if cv2 is None:
            self._cameras = []
            self._camera_combo.clear()
            self._camera_combo.setEnabled(False)
            self._refresh_btn.setEnabled(False)
            self._toggle_btn.setEnabled(False)
            self._set_source_status(
                "OpenCV (cv2) is not installed in the backend environment — "
                "camera selection is unavailable.", is_error=True
            )
            return

        was_live = self.is_live
        active_index = self._cameras[self._camera_combo.currentIndex()]["index"] \
            if self._cameras and self._camera_combo.currentIndex() >= 0 else None

        if was_live:
            self.toggle_live()  # stop cleanly before probing devices

        self._refresh_btn.setEnabled(False)
        self._src_lbl.setText("Detecting cameras…")
        try:
            self._cameras = self._detect_cameras()
        finally:
            self._refresh_btn.setEnabled(True)

        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        for cam in self._cameras:
            self._camera_combo.addItem(cam["label"])
        self._camera_combo.blockSignals(False)

        if not self._cameras:
            self._camera_combo.setEnabled(False)
            self._toggle_btn.setEnabled(False)
            self._set_source_status(
                "No camera detected — connect a webcam and click Refresh.",
                is_error=True
            )
            return

        self._camera_combo.setEnabled(True)
        self._toggle_btn.setEnabled(True)

        # Try to re-select the camera that was active before the refresh.
        restore_at = 0
        if active_index is not None:
            for i, cam in enumerate(self._cameras):
                if cam["index"] == active_index:
                    restore_at = i
                    break
        self._camera_combo.setCurrentIndex(restore_at)
        self._set_source_status(
            f"{len(self._cameras)} camera(s) detected — "
            f"select one and press Start Live Stream."
        )

    def _detect_cameras(self):
        """Probe device indices and return the ones that actually open.

        A camera "opens" only if VideoCapture reports isOpened() AND a frame
        can be read from it — some virtual/inactive devices open successfully
        but never deliver a frame, so both checks are required.
        
        Enhanced to display actual Windows camera device names when available.
        """
        found = []
        backend_pref = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0

        for index in range(MAX_CAMERAS_TO_PROBE):
            cap = None
            try:
                cap = cv2.VideoCapture(index, backend_pref) if backend_pref else cv2.VideoCapture(index)
                if not cap.isOpened():
                    continue
                ok, _ = cap.read()
                if not ok:
                    continue

                # Real device name (e.g. "Logitech BRIO"), from DirectShow's
                # own enumeration order — never fall back to the backend API
                # name (getBackendName() -> "DSHOW"), that's an API label,
                # not a device name.
                device_name = self._windows_camera_names.get(index) or f"Camera {index}"
                found.append({"index": index, "label": device_name})
            except Exception:
                # A misbehaving driver shouldn't take down camera detection.
                continue
            finally:
                if cap is not None:
                    cap.release()
        return found

    def _on_camera_selected(self, _row):
        # If we're mid-stream and the user switches cameras, hot-swap it —
        # BackendService.start_live() stops the previous session for us.
        if self.is_live:
            row = self._camera_combo.currentIndex()
            if 0 <= row < len(self._cameras):
                cam = self._cameras[row]
                w, h, fps = self._requested_resolution
                if self._backend.start_live(cam["index"], w, h, fps):
                    self._last_audit_count = 0
                    self.set_source_label(f"Source · {cam['label']}")
                    self._warn_if_resolution_not_granted(cam["label"])
                else:
                    QMessageBox.warning(
                        self, "Could not switch camera",
                        f"{cam['label']} could not be opened — it may be disconnected "
                        f"or in use by another application."
                    )

    def _on_resolution_selected(self, _row):
        self._requested_resolution = self._resolution_combo.currentData()
        # Hot-apply to an active stream the same way switching cameras does.
        if self.is_live:
            self._on_camera_selected(self._camera_combo.currentIndex())

    def _warn_if_resolution_not_granted(self, camera_label):
        """One-time heads-up if the camera/driver clamped the requested
        capture mode — common for 4K or 60fps requests on cheaper webcams.
        The ongoing per-frame status line always shows the true resolution
        regardless (decoded straight from the frame LiveSession produced),
        this is just an upfront explanation for why it's lower than asked.
        """
        session = self._backend.live_session
        if session is None or session.actual_resolution is None:
            return
        req_w, req_h, req_fps = session.requested_resolution or self._requested_resolution
        act_w, act_h, act_fps = session.actual_resolution
        if (act_w, act_h) != (req_w, req_h):
            QMessageBox.information(
                self, "Requested resolution not supported",
                f"{camera_label} does not support {req_w}×{req_h} — "
                f"it granted {act_w}×{act_h} instead. This is a hardware/driver "
                f"limit, not a bug."
            )

    def _set_source_status(self, text, is_error=False):
        self._src_lbl.setText(text)
        if is_error:
            styles.themed(
                self._src_lbl,
                lambda: f"color: {styles.ACCENT_RED}; font-size: 12px; font-weight: 600;"
            )
        else:
            styles.themed(
                self._src_lbl,
                lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 600;"
            )

    # ── Internal helpers ─────────────────────────────────────────────

    def _status_style(self):
        color = styles.ACCENT_TEAL if self.is_live else styles.MUTED_TEXT_COLOR
        return f"color: {color}; font-weight: bold; font-size: 13px;"

    def _fmt_elapsed(self):
        h = self._elapsed_secs // 3600
        m = (self._elapsed_secs % 3600) // 60
        s = self._elapsed_secs % 60
        return f"Elapsed  {h:02d}:{m:02d}:{s:02d}"

    def _tick_elapsed(self):
        """Called every second while the stream is 'live'. Only advances the
        real elapsed-time clock — it does not invent frames, detections, or
        redactions. Those arrive later from the backend via the public API."""
        self._elapsed_secs += 1
        self._elapsed_lbl.setText(self._fmt_elapsed())
        chunk_elapsed = self._elapsed_secs % 30
        self._chunk_len_lbl.setText(f"Chunk  {chunk_elapsed}/30s")

    def _add_audit_entry(self, index, ts, desc, kind):
        """Prepend a new audit entry to the log (newest first).

        The empty-state placeholder is only ever hidden-not-removed, so as
        entries keep getting inserted at index 0, the placeholder drifts
        toward the *end* of the layout. Once total items pass 50 the trim
        loop below (which removes from the end) eventually reaches and
        deletes the placeholder widget itself — after which the next call
        to this method crashes touching the now-deleted C++ object. Fixed
        by removing the placeholder for good the first time a real entry
        arrives, instead of just hiding it.
        """
        if self._audit_empty_state is not None:
            self._audit_inner_layout.removeWidget(self._audit_empty_state)
            self._audit_empty_state.deleteLater()
            self._audit_empty_state = None

        entry = _AuditEntry(index, ts, desc, kind)
        self._audit_inner_layout.insertWidget(0, entry)
        self._audit_count_lbl.setText(f"{len(self._audit_entries)} Events")

        # Trim to last 50 entries in the UI (keep memory low)
        while self._audit_inner_layout.count() > 50:
            item = self._audit_inner_layout.takeAt(self._audit_inner_layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

    # ── Camera open/close + live toggle ────────────────────────────────

    def _grab_frame(self):
        """Poll the backend's live session for its latest processed frame.

        All the actual work — capture, YOLO26 detection, TrOCR extraction,
        rule-based classification, the confidence-gated decision, and
        redaction — runs on LiveSession's own background thread
        (backend/src/live/session.py), completely off the GUI thread. This
        method only decodes whatever JPEG it last produced and paints it,
        plus mirrors over the running stats/audit log. That's what fixes
        the lag when starting a live stream: previously this ran the whole
        pipeline synchronously inside this 33ms QTimer tick, on the GUI
        thread, which stalled the UI on every detection pass.
        """
        if self._external_preview:
            return  # something else has taken over the preview feed

        session = self._backend.live_session
        if session is None or not session.is_live:
            self._handle_camera_dropped()
            return

        # Settings.py can transparently restart the live session (a new
        # LiveSession object) to apply changed thresholds/redaction method
        # — detect that here so the audit-log slice below doesn't skip
        # entries against a stale count from the previous session.
        if session is not self._last_seen_session:
            self._last_seen_session = session
            self._last_audit_count = 0

        jpeg = session.latest_frame_jpeg()
        if jpeg is not None:
            image = QImage.fromData(jpeg, "JPG")
            if not image.isNull():
                if self._camera_flipped:
                    image = image.mirrored(True, False)
                pixmap = QPixmap.fromImage(image)
                self._current_frame = pixmap
                self.set_preview_pixmap(pixmap)
                w, h = image.width(), image.height()
                self._set_source_status(f"Source · {self._camera_combo.currentText()} · {w}×{h}")

        stats = session.stats
        self._frames = stats.get("frames", self._frames)
        self._auto_redacted = stats.get("redacted", self._auto_redacted)
        self._flagged = stats.get("flagged", self._flagged)
        self._chunks = stats.get("chunks", self._chunks)
        self._stat_frames.set_value(self._frames)
        self._stat_redacted.set_value(self._auto_redacted)
        self._stat_flagged.set_value(self._flagged)
        self._stat_chunks.set_value(self._chunks)

        # Icons this page's _AuditEntry actually has ("id"/"credential"/
        # "license_plate" don't exist — see icon key list in components.py).
        icon_for_category = {
            "FACE": "face", "ID": "document", "DOCUMENT": "document",
            "CREDENTIAL": "card", "LICENSE_PLATE": "card",
        }
        audit_log = session.audit_log
        for entry in audit_log[self._last_audit_count:]:
            self.add_audit_entry(entry["description"], icon_for_category.get(entry.get("kind"), "face"))
        self._last_audit_count = len(audit_log)

    def _handle_camera_dropped(self):
        cam_label = self._camera_combo.currentText() or "the selected camera"
        self.toggle_live()  # stop cleanly
        self._set_source_status(
            f"Lost connection to {cam_label} — it may have been disconnected.",
            is_error=True
        )
        QMessageBox.warning(
            self, "Camera disconnected",
            f"Lost the video feed from {cam_label}. The live stream has been stopped."
        )

    def _flip_camera(self):
        """Toggle camera flip state."""
        self._camera_flipped = not self._camera_flipped
        if self.is_live and self._current_frame is not None:
            # Re-display current frame with new flip state
            self.set_preview_pixmap(self._current_frame)

    def _set_preview_scale(self, percent):
        """Resize the preview panel to `percent` of its base 320-400px
        height range. Previously this slider only updated its own "100%"
        label and never touched the actual preview widget."""
        scale = percent / 100.0
        min_h = max(180, int(360 * scale))
        max_h = max(min_h, int(640 * scale))
        self._preview_frame.setMinimumHeight(min_h)
        self._preview_frame.setMaximumHeight(max_h)
        self._webcam_lbl.setMinimumHeight(min_h)
        self._webcam_lbl.setMaximumHeight(max_h)
        if self._current_frame is not None:
            self.set_preview_pixmap(self._current_frame)

    def _set_preview_quality(self, percent):
        """Feed the Quality slider into the live pipeline's JPEG encode
        quality — backend/src/live/session.py reads AppConfig.jpeg_quality
        on every frame it produces. Previously this slider only updated
        its own "80%" label and never reached the backend."""
        self._backend.config.jpeg_quality = percent

    def toggle_live(self):
        """Starts/stops the live session.

        Starting hands the selected camera index to the shared
        BackendService, which opens it and runs the real pipeline on its
        own background thread (see backend/src/live/session.py) — this
        page just polls the resulting frames/stats/audit log on a timer.
        """
        if not self.is_live:
            # ── Starting ──
            if cv2 is None:
                QMessageBox.critical(
                    self, "Camera unavailable",
                    "OpenCV (cv2) is not installed in the backend environment, "
                    "so no camera can be opened."
                )
                return
            if not self._cameras:
                QMessageBox.warning(
                    self, "No camera available",
                    "No camera was detected. Connect a webcam and click Refresh, "
                    "then try again."
                )
                return
            row = self._camera_combo.currentIndex()
            if row < 0 or row >= len(self._cameras):
                return
            cam = self._cameras[row]
            w, h, fps = self._requested_resolution
            if not self._backend.start_live(cam["index"], w, h, fps):
                QMessageBox.warning(
                    self, "Could not start camera",
                    f"{cam['label']} could not be opened — it may be disconnected "
                    f"or in use by another application."
                )
                self._set_source_status(f"Could not open {cam['label']}.", is_error=True)
                return

            self.is_live = True
            self._external_preview = False
            self._last_audit_count = 0
            self.set_source_label(f"Source · {cam['label']}")
            self._status_lbl.setText("● Live Stream Active")
            self._toggle_btn.setText("  Stop Live Stream")
            self._toggle_btn.setIcon(create_icon("close", "#FFFFFF", 16))
            self._camera_combo.setEnabled(True)  # allow hot-swap while live
            self._refresh_btn.setEnabled(False)  # avoid probing devices mid-stream
            self._session_timer.start()
            self._frame_timer.start()
            self._warn_if_resolution_not_granted(cam["label"])
        else:
            # ── Stopping ──
            self.is_live = False
            self._frame_timer.stop()
            self._session_timer.stop()
            self._backend.stop_live()
            self._webcam_lbl.setPixmap(QPixmap())
            self._webcam_lbl.setText("Live preview is off")
            self._status_lbl.setText("● Offline")
            self._toggle_btn.setText("  Start Live Stream")
            self._toggle_btn.setIcon(create_icon("play", "#FFFFFF", 16))
            self._refresh_btn.setEnabled(True)
            if self._cameras:
                self.set_source_label(
                    f"{len(self._cameras)} camera(s) detected — "
                    f"select one and press Start Live Stream."
                )

        self._status_lbl.setStyleSheet(self._status_style())

    def retheme(self):
        retheme_widget_tree(self)
        # The Live Monitoring preview always stays black regardless of theme,
        # so re-assert it after a theme switch instead of letting it inherit
        # the app palette.
        self._preview_frame.setStyleSheet(
            "background-color: #000000; border-radius: 12px;"
        )
        self._webcam_lbl.setStyleSheet(
            "background-color: #000000; border-radius: 12px; color: #E8EAED; font-weight: 600;"
        )
        # Refresh the empty state component (only present until the first
        # real audit entry ever arrives — see _add_audit_entry).
        if self._audit_empty_state is not None:
            self._audit_empty_state.retheme()

    def closeEvent(self, event):
        self._session_timer.stop()
        self._frame_timer.stop()
        self._backend.stop_live()
        super().closeEvent(event)

    # === PUBLIC API ===
    # Kept as a clean external surface (e.g. for tests, or another page
    # temporarily overriding the preview) — not used to fabricate data.

    def set_source_label(self, text):
        """Update the source banner, e.g. 'Source · Logitech C920 @ 30 FPS'."""
        self._set_source_status(text, is_error=False)

    def set_preview_pixmap(self, pixmap):
        """Push a decoded frame (QPixmap) into the preview panel."""
        scaled = pixmap.scaled(
            self._webcam_lbl.width(), self._webcam_lbl.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._webcam_lbl.setPixmap(scaled)

    def take_over_preview(self):
        """Let something other than this page's own polling own the
        preview panel — stops the frame-poll timer without touching the
        Live/Offline session state or the backend's live session itself.
        """
        self._external_preview = True
        self._frame_timer.stop()

    def set_stream_active(self, active):
        """Let the backend drive the Offline/Live visual state directly."""
        if active != self.is_live:
            self.toggle_live()

    def set_live_stats(self, chunks=None, frames=None, redacted=None, flagged=None):
        """Update the live stat tiles with real backend values."""
        if chunks is not None:
            self._chunks = chunks
            self._stat_chunks.set_value(chunks)
        if frames is not None:
            self._frames = frames
            self._stat_frames.set_value(frames)
        if redacted is not None:
            self._auto_redacted = redacted
            self._stat_redacted.set_value(redacted)
        if flagged is not None:
            self._flagged = flagged
            self._stat_flagged.set_value(flagged)

    def add_audit_entry(self, description, kind="face"):
        """Append one real detection/redaction event to the audit log."""
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        index = len(self._audit_entries) + 1
        self._audit_entries.append((index, ts, description, kind))
        self._add_audit_entry(index, ts, description, kind)