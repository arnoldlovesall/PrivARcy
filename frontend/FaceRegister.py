# FaceRegister.py
import os, sys
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QFileDialog, QGridLayout, QDialog,
                             QMessageBox, QComboBox, QLineEdit)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
import styles
from components import create_icon, retheme_widget_tree, load_scaled_pixmap, NotificationBanner, create_scrollable_container, EmptyState

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    import cv2
except ImportError:
    cv2 = None

IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff)"


def _hex_to_bgr(hex_color):
    """'#2AB3A6' -> (166, 179, 42) for cv2, which expects BGR not RGB."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (b, g, r)


class FaceVerificationDialog(QDialog):
    """Face Verification Dialog - styled like GCash fintech interface.
    
    Allows users to verify a participant's identity using face recognition.
    Features a clean, modern UI with status indicators and confidence scoring.
    """
    def __init__(self, participant, verify_result, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Verify Face - {participant['name']}")
        self.resize(500, 600)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {styles.BG_COLOR};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Header with participant info
        header_card = QFrame()
        header_card.setObjectName("Card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(12)
        
        title_lbl = QLabel("Face Recognition Verification")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        header_layout.addWidget(title_lbl)
        
        desc_lbl = QLabel(f"Verifying identity for {participant['name']} (Code: {participant['code']})")
        styles.themed(desc_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        header_layout.addWidget(desc_lbl)
        layout.addWidget(header_card)
        
        # Face preview section
        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(20, 20, 20, 20)
        preview_layout.setSpacing(12)
        
        preview_label = QLabel("Registered Face")
        preview_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        preview_layout.addWidget(preview_label)
        
        face_frame = QLabel()
        face_frame.setObjectName("Card")
        face_frame.setFixedHeight(200)
        face_frame.setAlignment(Qt.AlignCenter)
        styles.themed(face_frame, lambda: f"background-color: {styles.BORDER_COLOR}; border-radius: 12px;")
        
        pixmap = load_scaled_pixmap(participant.get("path"), 200, 200) if participant.get("path") else None
        if pixmap is not None:
            face_frame.setPixmap(pixmap)
        else:
            face_frame.setPixmap(create_icon("face", styles.MUTED_TEXT_COLOR, 80).pixmap(80, 80))
        
        preview_layout.addWidget(face_frame)
        layout.addWidget(preview_card)
        
        # Status section
        status_card = QFrame()
        status_card.setObjectName("Card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(12)
        
        status_title = QLabel("Verification Status")
        status_title.setStyleSheet("font-size: 13px; font-weight: 600;")
        status_layout.addWidget(status_title)
        
        # Real result from FaceRegistry.verify() — a self-consistency check
        # (does this registry entry still match its own source photo?)
        # computed via face_recognition, not a hard-coded number.
        matched = verify_result.get("matched", False)
        confidence = verify_result.get("confidence", 0.0)
        if matched:
            self.status_lbl = QLabel(f"\u2713 Verified | Confidence: {confidence:.1f}%")
            self.status_lbl.setStyleSheet(f"font-size: 12px; color: {styles.ACCENT_TEAL}; font-weight: 600;")
        else:
            self.status_lbl = QLabel(f"\u2717 Not Verified | Confidence: {confidence:.1f}%")
            self.status_lbl.setStyleSheet(f"font-size: 12px; color: {styles.ACCENT_RED}; font-weight: 600;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_lbl)
        
        details_lbl = QLabel(verify_result.get("message", ""))
        styles.themed(details_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 11px;")
        details_lbl.setWordWrap(True)
        details_lbl.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(details_lbl)
        layout.addWidget(status_card)
        
        layout.addStretch()
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setFixedHeight(44)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        confirm_btn = QPushButton("Confirm Verification")
        confirm_btn.setObjectName("PrimaryButton")
        confirm_btn.setFixedHeight(44)
        confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(confirm_btn)
        
        layout.addLayout(btn_layout)


class ParticipantCard(QFrame):
    def __init__(self, participant, on_remove, on_verify=None):
        super().__init__()
        self.setObjectName("Card")
        self.participant = participant
        self.reg_time = participant.get("date")  # datetime object
        self.on_verify = on_verify

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header with Code Tag and Status
        top_row = QHBoxLayout()
        code_lbl = QLabel(participant["code"])
        code_lbl.setObjectName("CodeTag")
        status_lbl = QLabel("Consented")
        status_lbl.setObjectName("PillTeal")
        top_row.addWidget(code_lbl)
        top_row.addStretch()
        top_row.addWidget(status_lbl)
        layout.addLayout(top_row)

        # Photo Preview Container
        photo = QLabel()
        photo.setObjectName("PhotoPreview")
        photo.setFixedHeight(120)
        photo.setAlignment(Qt.AlignCenter)

        pixmap = load_scaled_pixmap(participant.get("path"), 200, 120) if participant.get("path") else None
        if pixmap is not None:
            photo.setPixmap(pixmap)
        else:
            photo.setPixmap(create_icon("avatar", styles.MUTED_TEXT_COLOR, 44).pixmap(44, 44))
            styles.themed(photo, lambda: f"background-color: {styles.BORDER_COLOR}; border-radius: 10px;")
            photo._retheme_icon = lambda: photo.setPixmap(
                create_icon("avatar", styles.MUTED_TEXT_COLOR, 44).pixmap(44, 44)
            )

        layout.addWidget(photo)

        # Info
        name_lbl = QLabel(participant["name"])
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(name_lbl)

        # Real‑time label: shows exact date/time (with seconds & AM/PM) + relative time
        self._date_lbl = QLabel()
        self._date_lbl.setAlignment(Qt.AlignCenter)
        self._date_lbl.setStyleSheet("font-size: 11px;")
        styles.themed(self._date_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self._date_lbl)

        self._update_datetime_label()
        # No per-card QTimer here — see FaceRegisterPage._tick_relative_times,
        # which drives every visible card's label from a single shared
        # timer instead of each card running its own 1Hz QTimer. With
        # enough registered participants, N independent timers each doing
        # string formatting every second adds up to real, unnecessary
        # overhead for a label that's only ever cosmetic.

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        
        verify_btn = QPushButton("Verify")
        verify_btn.setObjectName("PrimaryButton")
        verify_btn.setFixedHeight(36)
        verify_btn.setIcon(create_icon("face", "#FFFFFF", 14))
        verify_btn.clicked.connect(self._on_verify_clicked)
        btn_layout.addWidget(verify_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("DangerButton")
        remove_btn.setFixedHeight(36)
        remove_btn.clicked.connect(lambda: on_remove(self.participant["code"]))
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)

    def _update_datetime_label(self):
        """Update label with exact date/time and relative time."""
        if not self.reg_time:
            self._date_lbl.setText("Registered: unknown")
            return
        exact = self.reg_time.strftime("%b %d, %Y at %I:%M:%S %p")
        relative = self._relative_time(self.reg_time)
        self._date_lbl.setText(f"Registered on {exact} ({relative})")

    def _relative_time(self, dt):
        """Return a human‑readable relative time string (with seconds precision)."""
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return "in the future"  # just in case
        if seconds < 60:
            return f"{seconds} second{'s' if seconds != 1 else ''} ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        if days < 7:
            return f"{days} day{'s' if days != 1 else ''} ago"
        return f"{days} days ago"

    def _on_verify_clicked(self):
        """Handle verify button click."""
        if self.on_verify:
            self.on_verify(self.participant)


class FaceScanDialog(QDialog):
    """Live-camera face enrollment with blink-based liveness verification.

    Uses the same face-matching engine (face_recognition, via
    FaceRegistry) that Live.py's redaction pipeline uses for consent
    matching — a participant enrolled here is recognized there with no
    separate code path. Requires one full blink before capturing, so a
    printed photo or a static image held up to the camera can't be used
    to enroll a face that was never actually present.
    """
    STATE_SEARCHING = "searching"     # no face, or more than one
    STATE_HOLD_STILL = "hold_still"   # exactly one face, framed — waiting for a blink
    STATE_CAPTURED = "captured"       # blink observed, frame captured

    def __init__(self, backend, cameras, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Face — Live Enrollment")
        self.setMinimumSize(560, 620)
        self._backend = backend
        self._cameras = cameras
        self._cap = None
        self._state = self.STATE_SEARCHING
        self._blink_detector = None
        self._captured_frame = None
        self.result_path = None
        self._scan_angle = 0  # drives the rotating dotted ring

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Participant name")
        form_row.addWidget(self.name_input)
        self.camera_combo = QComboBox()
        for cam in cameras:
            self.camera_combo.addItem(cam["label"], cam["index"])
        form_row.addWidget(self.camera_combo)
        layout.addLayout(form_row)

        self.preview_lbl = QLabel("Starting camera…")
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        self.preview_lbl.setStyleSheet("background-color: #000; border-radius: 10px; color: white;")
        self.preview_lbl.setMinimumHeight(400)
        layout.addWidget(self.preview_lbl)

        self.status_lbl = QLabel("Position your face in frame.")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.clicked.connect(self._restart_scan)
        self.retry_btn.setEnabled(False)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("Use This Photo")
        self.confirm_btn.setObjectName("PrimaryButton")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(self.retry_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame)
        self._open_camera()

    def _open_camera(self):
        if cv2 is None or not self._cameras:
            self.status_lbl.setText("No camera available.")
            return
        index = self.camera_combo.currentData()
        backend_pref = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
        self._cap = cv2.VideoCapture(index, backend_pref) if backend_pref else cv2.VideoCapture(index)
        if not self._cap.isOpened():
            self.status_lbl.setText("Could not open the selected camera.")
            return
        from src.face import FaceRegistry
        self._blink_detector = FaceRegistry.BlinkDetector()
        self._state = self.STATE_SEARCHING
        self.timer.start(33)

    def _restart_scan(self):
        self.confirm_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        self._captured_frame = None
        self._open_camera()

    def _on_frame(self):
        if self._cap is None or self._state == self.STATE_CAPTURED:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self.status_lbl.setText("Camera feed lost.")
            self.timer.stop()
            return

        from src.face import FaceRegistry
        try:
            faces = FaceRegistry.detect_faces_with_landmarks(frame)
        except RuntimeError as exc:
            self.status_lbl.setText(str(exc))
            self.timer.stop()
            return

        if len(faces) != 1:
            self._state = self.STATE_SEARCHING
            self.status_lbl.setText(
                "No face detected — move into frame." if not faces
                else "More than one face detected — only one person at a time."
            )
        else:
            self._state = self.STATE_HOLD_STILL
            face = faces[0]

            if self._blink_detector.update(face["ear"]):
                # Blink completed — this is the liveness signal. Capture
                # this frame right now, before the eyes finish reopening.
                self._captured_frame = frame.copy()
                self._state = self.STATE_CAPTURED
                self.timer.stop()
                self.status_lbl.setText("✓ Liveness verified — blink detected. Review and confirm below.")
                self.confirm_btn.setEnabled(True)
                self.retry_btn.setEnabled(True)
            else:
                self.status_lbl.setText("Face detected — please blink naturally to verify liveness.")

            self._draw_scanner_overlay(frame, face["bbox"])

        self._show_frame(frame)

    def _draw_scanner_overlay(self, frame, bbox):
        """Corner-bracket viewfinder + rotating dotted scan ring + status
        text, drawn straight onto the frame — the same visual language as
        a biometric-scanner UI, using the app's actual teal accent color
        rather than a fixed color, so it matches whichever theme is active.
        """
        left, top, right, bottom = bbox
        cx, cy = (left + right) // 2, (top + bottom) // 2
        # Square region padded around the detected face, so the frame
        # reads consistently regardless of the face's own aspect ratio.
        side = int(max(right - left, bottom - top) * 1.6)
        half = side // 2
        x1, y1, x2, y2 = cx - half, cy - half, cx + half, cy + half

        teal = _hex_to_bgr(styles.ACCENT_TEAL)
        captured = self._state == self.STATE_CAPTURED
        ring_color = (120, 220, 140) if captured else teal  # green once verified
        thickness = 3

        # Corner brackets (L-shaped), one per corner of the square.
        bracket_len = max(20, side // 6)
        corners = [
            ((x1, y1), (1, 0), (0, 1)),   # top-left: right, down
            ((x2, y1), (-1, 0), (0, 1)),  # top-right: left, down
            ((x1, y2), (1, 0), (0, -1)),  # bottom-left: right, up
            ((x2, y2), (-1, 0), (0, -1)), # bottom-right: left, up
        ]
        for (px, py), (dx1, dy1), (dx2, dy2) in corners:
            cv2.line(frame, (px, py), (px + dx1 * bracket_len, py + dy1 * bracket_len), teal, thickness)
            cv2.line(frame, (px, py), (px + dx2 * bracket_len, py + dy2 * bracket_len), teal, thickness)

        # Rotating dotted ring, inscribed in the square — animates via
        # self._scan_angle, incremented once per frame below.
        radius = half - 6
        if radius > 10:
            num_dashes = 24
            dash_deg = 360 / num_dashes / 2
            for i in range(num_dashes):
                start = (self._scan_angle + i * (360 / num_dashes)) % 360
                cv2.ellipse(frame, (cx, cy), (radius, radius), 0, start, start + dash_deg, ring_color, 2)
        self._scan_angle = (self._scan_angle + 3) % 360

        # "FACE DETECTED" / participant name, under the bracket frame —
        # only drawn once there's an actual name typed in, so it isn't
        # showing a misleading placeholder.
        label = "LIVENESS VERIFIED" if captured else "FACE DETECTED"
        cv2.putText(frame, label, (x1, y2 + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, ring_color, 2, cv2.LINE_AA)
        name = self.name_input.text().strip()
        if name:
            cv2.putText(frame, f'"{name}"', (x1, y2 + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ring_color, 1, cv2.LINE_AA)

    def _show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.preview_lbl.width(), self.preview_lbl.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.preview_lbl.setPixmap(pixmap)

    def _confirm(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Enter a participant name before saving.")
            return
        if self._captured_frame is None:
            return

        existing = len(self._backend.list_faces())
        code = f"P-{existing + 1:03d}"
        dest = self._backend.config.registry_dir / f"{code}.jpg"
        cv2.imwrite(str(dest), self._captured_frame)

        try:
            self._backend.register_face(code, name, str(dest))
        except Exception as exc:
            dest.unlink(missing_ok=True)
            QMessageBox.critical(self, "Registration failed", str(exc))
            return

        self.result_path = str(dest)
        self.result_name = name
        self.accept()

    def closeEvent(self, event):
        self.timer.stop()
        if self._cap is not None:
            self._cap.release()
        super().closeEvent(event)

    def reject(self):
        self.timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        super().reject()


class FaceRegisterPage(QWidget):
    def __init__(self, backend):
        super().__init__()
        # Shared with every other page via MainWindow — see Process.py for
        # why a page-local BackendService() was wrong (diverging registries).
        self._backend = backend
        self.participants = self._load_participants()

        # One shared timer drives every visible ParticipantCard's relative-
        # time label, instead of each card running its own QTimer.
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_relative_times)
        self._clock_timer.start(1000)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(20)

        # Required Header Section
        header_section = QVBoxLayout()
        header_section.setSpacing(4)
        heading = QLabel("Registered Participants")
        heading.setObjectName("PageTitle")
        desc = QLabel(
            "Consented faces are registered under anonymous participant codes. "
            "Everyone else is treated as a bystander and redacted by default."
        )
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        header_section.addWidget(heading)
        header_section.addWidget(desc)
        main_layout.addLayout(header_section)

        # Action bar
        action_bar = QHBoxLayout()
        add_photo_btn = QPushButton("  Register Face from Photo")
        add_photo_btn.setObjectName("PrimaryButton")
        add_photo_btn.setIcon(create_icon("face", "#FFFFFF", 18))
        add_photo_btn.clicked.connect(self.add_face)
        action_bar.addWidget(add_photo_btn)

        # Live camera enrollment with blink-based liveness verification —
        # uses the same face-matching engine (face_recognition, via
        # FaceRegistry) Live.py's redaction pipeline uses for consent
        # matching, so a participant registered here is recognized there.
        scan_btn = QPushButton("  Scan Face (Live)")
        scan_btn.setObjectName("PrimaryButton")
        scan_btn.setIcon(create_icon("scan", "#FFFFFF", 18))
        scan_btn.clicked.connect(self.scan_face)
        action_bar.addWidget(scan_btn)

        # Verify button - new GCash-style feature
        verify_btn = QPushButton("  Verify with Face Recognition")
        verify_btn.setObjectName("PrimaryButton")
        verify_btn.setIcon(create_icon("check", "#FFFFFF", 18))
        verify_btn.clicked.connect(self.verify_face_recognition)
        action_bar.addWidget(verify_btn)

        format_pill = QLabel(
            "Supported Formats: PNG · JPG · JPEG · BMP · WEBP · GIF · TIFF"
        )
        styles.themed(format_pill, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; margin-left: 10px;")
        action_bar.addWidget(format_pill)
        action_bar.addStretch()

        self.count_badge = QLabel(f"{len(self.participants)} Registered")
        self.count_badge.setObjectName("PillTeal")
        action_bar.addWidget(self.count_badge)

        main_layout.addLayout(action_bar)

        self.banner = NotificationBanner()
        main_layout.addWidget(self.banner)

        # Registered Participants Grid
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(16)
        main_layout.addWidget(self.grid_container)

        # Empty state using reusable component
        self.empty_state = EmptyState(
            title="No Participants Registered",
            description="All detected faces in the video will be redacted. Register participants to keep them visible.",
            icon_name="face"
        )
        self.empty_state.hide()
        main_layout.addWidget(self.empty_state)

        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

        self.refresh_grid()

    def scan_face(self):
        """Live-camera enrollment via FaceScanDialog — same underlying
        face-matching engine (face_recognition) Live.py uses for consent
        matching, plus blink-based liveness verification before capture."""
        if cv2 is None:
            QMessageBox.critical(self, "Camera unavailable", "OpenCV (cv2) is not installed.")
            return
        cameras = self._backend.discover_cameras()
        if not cameras:
            QMessageBox.warning(self, "No camera available", "No camera was detected.")
            return

        dialog = FaceScanDialog(self._backend, cameras, self)
        if dialog.exec_() == QDialog.Accepted:
            self.participants = self._load_participants()
            self.refresh_grid()
            self.banner.show_message(f"Registered {dialog.result_name} via live scan.", "success")

    def add_face(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Face Photos (PNG, JPG, JPEG, BMP, WEBP, GIF, TIFF)",
            "",
            IMAGE_FILE_FILTER
        )
        if not files:
            return

        added = 0
        next_serial = len(self.participants) + 1
        for path in files:
            name = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            next_code = f"P-{next_serial:03d}"
            now = datetime.now()  # includes seconds
            try:
                # Registration stores an actual face embedding. A photo with
                # no face or multiple faces is rejected instead of pretending
                # that a participant was enrolled.
                self._backend.register_face(next_code, name, path)
                self.participants.append({"code": next_code, "name": name, "path": path, "date": now})
                added += 1
                # Only advance the serial on success — otherwise a failed
                # photo mid-batch (e.g. dlib not loading) would make the
                # *next* photo reuse the same "P-00N" code, since it was
                # previously derived from len(self.participants), which a
                # failed registration never grows.
                next_serial += 1
            except Exception as exc:
                self.banner.show_message(f"Could not register {os.path.basename(path)}: {exc}", "error")

        self.refresh_grid()
        if added:
            self.banner.show_message(f"Successfully registered {added} new participant(s).", "success")

    def verify_face_recognition(self):
        """Launch face recognition verification for registered participants."""
        if not self.participants:
            self.banner.show_message("No participants to verify. Register a face first.", "warning")
            return

        # For demo: verify the first participant
        participant = self.participants[0]
        self._run_verification(participant)

    def remove_face(self, code):
        self._backend.remove_face(code)
        self.participants = [p for p in self.participants if p["code"] != code]
        self.refresh_grid()
        self.banner.show_message(f"Removed participant {code}.", "info")

    def on_participant_verify(self, participant):
        """Handle participant verification request."""
        self._run_verification(participant)

    def _run_verification(self, participant):
        verify_result = self._backend.verify_face(participant["code"])
        dialog = FaceVerificationDialog(participant, verify_result, self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            if verify_result.get("matched"):
                self.banner.show_message(f"\u2713 Verified {participant['name']}", "success")
            else:
                self.banner.show_message(f"Verification failed for {participant['name']}.", "warning")

    def _load_participants(self):
        """Load real registered participants from the backend instead of
        starting from the mock participant list it originally shipped with."""
        participants = []
        for record in self._backend.list_faces():
            registered_at = record.get("registered_at")
            try:
                date = datetime.fromisoformat(registered_at) if registered_at else None
            except ValueError:
                date = None
            participants.append({
                "code": record["code"], "name": record["name"],
                "path": record.get("image_path"), "date": date,
            })
        return participants

    def refresh_grid(self):
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.count_badge.setText(f"{len(self.participants)} Registered")

        if not self.participants:
            self.empty_state.show()
            self.grid_container.hide()
            self._cards = []
            return

        self.empty_state.hide()
        self.grid_container.show()
        columns = 4
        self._cards = []
        for i, participant in enumerate(self.participants):
            row, col = divmod(i, columns)
            card = ParticipantCard(participant, self.remove_face, self.on_participant_verify)
            self.grid_layout.addWidget(card, row, col)
            self._cards.append(card)

    def _tick_relative_times(self):
        """Refresh every visible card's relative-time label from one
        shared timer, instead of each ParticipantCard running its own."""
        for card in getattr(self, "_cards", []):
            card._update_datetime_label()

    def retheme(self):
        retheme_widget_tree(self)
        if hasattr(self, 'empty_state'):
            self.empty_state.retheme()
        self.refresh_grid()
