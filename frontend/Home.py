# Home.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
                             QPushButton, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal
import styles
from components import create_icon, StatCard, retheme_widget_tree, create_scrollable_container, EmptyState


class SelectableCard(QFrame):
    """A clickable card used for exclusive source selection."""
    clicked = pyqtSignal(object)

    def __init__(self, title, desc, icon_name, parent=None):
        super().__init__(parent)
        self.setObjectName("SelectableCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.icon_name = icon_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 28).pixmap(28, 28))
        self.icon_lbl._retheme_icon = lambda: self.icon_lbl.setPixmap(
            create_icon(self.icon_name, styles.ACCENT_TEAL, 28).pixmap(28, 28))
        layout.addWidget(self.icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
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


class ConfigOptionCard(QFrame):
    """Option card for Processing Configuration with radio indicator & description."""
    clicked = pyqtSignal(object)

    def __init__(self, title, desc, badge_text=None, parent=None):
        super().__init__(parent)
        self.setObjectName("OptionCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.value = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        self.radio_dot = QLabel("○")
        styles.themed(self.radio_dot, self._radio_style)
        top_row.addWidget(self.radio_dot)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()

        if badge_text:
            badge = QLabel(badge_text)
            badge.setObjectName("PillTeal")
            top_row.addWidget(badge)

        layout.addLayout(top_row)

        desc_lbl = QLabel(desc)
        styles.themed(desc_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

    def _radio_style(self):
        is_sel = self.property("selected")
        color = styles.ACCENT_TEAL if is_sel else styles.MUTED_TEXT_COLOR
        return f"color: {color}; font-size: 16px; font-weight: bold;"

    def set_selected(self, selected):
        self.setProperty("selected", selected)
        self.radio_dot.setText("●" if selected else "○")
        self.radio_dot.setStyleSheet(self._radio_style())
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self)
        super().mousePressEvent(event)


class HomePage(QWidget):
    def __init__(self, navigate_callback):
        super().__init__()
        self.navigate = navigate_callback

        # Main wrapper layout that holds the scroll area
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # Content widget
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 20)
        layout.setSpacing(22)

        # Dashboard Overview Stats
        # NOTE: these start at zero/placeholder because there is no backend
        # yet to report real history from. Kept as named attributes (not
        # hard-coded numbers) so a future backend can populate them via
        # set_overview_stats() below without conflicting with fake defaults.
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        self.stat_processed = StatCard("process", "Videos Processed", "0", "No data yet")
        self.stat_faces = StatCard("face", "Registered Faces", "0", "No data yet")
        self.stat_pending = StatCard("review", "Pending Review", "0", "No data yet")
        self.stat_confidence = StatCard("speed", "Avg. Confidence", "—", "No data yet")
        stats_layout.addWidget(self.stat_processed)
        stats_layout.addWidget(self.stat_faces)
        stats_layout.addWidget(self.stat_pending)
        stats_layout.addWidget(self.stat_confidence)
        layout.addLayout(stats_layout)

        # Section: Select Video Input
        input_section = QVBoxLayout()
        input_section.setSpacing(4)
        heading = QLabel("Select Video Input")
        heading.setObjectName("SectionHeading")
        input_desc = QLabel("Choose where the footage comes from and how thoroughly PrivARcy should scan it. Nothing is analyzed until you continue.")
        input_desc.setObjectName("SectionHelper")
        input_desc.setWordWrap(True)
        input_section.addWidget(heading)
        input_section.addWidget(input_desc)
        layout.addLayout(input_section)

        # Source Selection Cards
        source_layout = QHBoxLayout()
        source_layout.setSpacing(15)
        self.video_card = SelectableCard("Video Files", "MP4, AVI, MOV. Single or batch upload.", "video")
        self.webcam_card = SelectableCard("Webcam", "Built-in or external USB cameras.", "webcam")
        self.mobile_card = SelectableCard("Mobile Camera", "Pair a phone over local network (RTSP).", "mobile")

        self.source_cards = [self.video_card, self.webcam_card, self.mobile_card]
        for card in self.source_cards:
            card.clicked.connect(self.select_source_card)
        self.video_card.set_selected(True)

        source_layout.addWidget(self.video_card)
        source_layout.addWidget(self.webcam_card)
        source_layout.addWidget(self.mobile_card)
        layout.addLayout(source_layout)

        # File Browser Row
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Selected Files: "))
        self.file_label = QLabel("None selected")
        styles.themed(self.file_label, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-weight: 500;")
        file_row.addWidget(self.file_label)
        file_row.addStretch()
        browse_btn = QPushButton("Browse Files")
        browse_btn.setObjectName("SecondaryButton")
        browse_btn.clicked.connect(self.browse_files)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Section: Processing Configuration
        config_section = QVBoxLayout()
        config_section.setSpacing(8)
        config_heading = QLabel("Processing Configuration")
        config_heading.setObjectName("SectionHeading")
        config_section.addWidget(config_heading)

        config_cards_layout = QHBoxLayout()
        config_cards_layout.setSpacing(15)

        self.opt_high_card = ConfigOptionCard(
            "High Accuracy · Offline",
            "Full pipeline, every stage. GPU recommended.",
            "GPU Recommended"
        )
        self.opt_lite_card = ConfigOptionCard(
            "Lightweight · Real-Time",
            "Trimmed model set. Targets >15 FPS on CPU or entry-level GPU.",
            "Target >15 FPS"
        )
        self.config_options = [self.opt_high_card, self.opt_lite_card]
        for c in self.config_options:
            c.clicked.connect(self.select_config_card)
        self.opt_high_card.set_selected(True)

        config_cards_layout.addWidget(self.opt_high_card)
        config_cards_layout.addWidget(self.opt_lite_card)
        config_section.addLayout(config_cards_layout)
        layout.addLayout(config_section)

        # Continue Button
        continue_btn = QPushButton("Continue to Processing")
        continue_btn.setObjectName("PrimaryButton")
        continue_btn.setFixedHeight(48)
        continue_btn.clicked.connect(lambda: self.navigate("Process"))
        layout.addWidget(continue_btn)

        # Before You Start
        layout.addSpacing(10)
        b4_heading = QLabel("Before You Start")
        b4_heading.setObjectName("SectionHeading")
        layout.addWidget(b4_heading)

        b4_layout = QHBoxLayout()
        b4_layout.setSpacing(15)
        card1 = self.create_pre_step("1", "Register faces", "Add anyone who should be kept visible in Face Register — everyone else gets redacted by default.", "Go to Face Register", "Face Register")
        card2 = self.create_pre_step("2", "Set thresholds", "Confidence and redaction-style defaults live in Settings.", "Go to Settings", "Settings")
        card3 = self.create_pre_step("3", "Review low-confidence hits", "Anything under the high threshold waits for you in the Review queue.", "Go to Review Queue", "Review")

        b4_layout.addWidget(card1)
        b4_layout.addWidget(card2)
        b4_layout.addWidget(card3)
        layout.addLayout(b4_layout)

        # Recent Activity — processing history (see BackendService.history_store)
        layout.addSpacing(10)
        history_heading = QLabel("Recent Activity")
        history_heading.setObjectName("SectionHeading")
        layout.addWidget(history_heading)

        self._history_card = QFrame()
        self._history_card.setObjectName("Card")
        self._history_layout = QVBoxLayout(self._history_card)
        self._history_layout.setContentsMargins(18, 18, 18, 18)
        self._history_layout.setSpacing(10)

        self._history_empty = EmptyState(
            "No videos processed yet",
            "Finished jobs will show up here — source name, when, and how much was redacted.",
            "history",
        )
        self._history_layout.addWidget(self._history_empty)
        layout.addWidget(self._history_card)

        layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

    def create_pre_step(self, num, title, desc, btn_text, target_page):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        num_lbl = QLabel(num)
        styles.themed(num_lbl, lambda: f"background-color: {styles.ACCENT_ORANGE}; color: white; border-radius: 12px; font-weight: bold; font-size: 12px;")
        num_lbl.setFixedSize(24, 24)
        num_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(num_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        styles.themed(desc_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn = QPushButton(btn_text)
        btn.setObjectName("SecondaryButton")
        btn.clicked.connect(lambda: self.navigate(target_page))
        layout.addWidget(btn)

        return card

    def select_source_card(self, chosen_card):
        for card in self.source_cards:
            card.set_selected(card is chosen_card)

    def select_config_card(self, chosen_card):
        for card in self.config_options:
            card.set_selected(card is chosen_card)

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Video Files", "", "Video Files (*.mp4 *.avi *.mov)")
        if files:
            self.file_label.setText(f"{len(files)} file(s) selected")

    def retheme(self):
        retheme_widget_tree(self)

    # === PUBLIC API FOR FUTURE BACKEND ===
    def set_overview_stats(self, processed=None, faces=None, pending=None, confidence=None):
        """Update the dashboard overview tiles with real backend values.

        Any argument left as None leaves that tile untouched. Values are
        passed through as-is (already-formatted strings or numbers).
        """
        if processed is not None:
            self.stat_processed.set_value(processed)
        if faces is not None:
            self.stat_faces.set_value(faces)
        if pending is not None:
            self.stat_pending.set_value(pending)
        if confidence is not None:
            self.stat_confidence.set_value(confidence)

    def set_history(self, entries):
        """Public API: populate Recent Activity from
        BackendService.get_history(). Each entry is a dict with
        source_name, processed_at, frames, total_detections, redactions."""
        for row in getattr(self, "_history_rows", []):
            self._history_layout.removeWidget(row)
            row.deleteLater()
        self._history_rows = []

        if not entries:
            self._history_empty.show()
            return
        self._history_empty.hide()

        for entry in entries:
            row = QHBoxLayout()
            name_lbl = QLabel(entry.get("source_name", "Unknown"))
            name_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
            time_lbl = QLabel(entry.get("processed_at", ""))
            styles.themed(time_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
            detail_lbl = QLabel(
                f"{entry.get('total_detections', 0)} detections · {entry.get('redactions', 0)} redacted"
            )
            styles.themed(detail_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")

            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(detail_lbl)
            row.addSpacing(12)
            row.addWidget(time_lbl)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self._history_layout.addWidget(row_widget)
            self._history_rows.append(row_widget)

