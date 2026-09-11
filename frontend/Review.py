# Review.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QDialog)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
import styles
from components import (create_icon, retheme_widget_tree, load_scaled_pixmap,
                        create_scrollable_container, EmptyState)

STATUS_LABELS = {
    "pending": "Pending Review",
    "confirmed": "Confirmed",
    "rejected": "Rejected / Not Required",
}
STATUS_PILL_OBJECT = {
    "pending": "PillOrange",
    "confirmed": "PillTeal",
    "rejected": "PillRed",
}


def status_pill(status):
    lbl = QLabel(STATUS_LABELS.get(status, "Pending Review"))
    lbl.setObjectName(STATUS_PILL_OBJECT.get(status, "PillOrange"))
    return lbl


def confidence_pill(confidence):
    """Create a colored confidence badge."""
    pct = f"{confidence * 100:.0f}%"
    lbl = QLabel(f"Confidence: {pct}")
    if confidence >= 0.7:
        lbl.setObjectName("PillTeal")
    elif confidence >= 0.6:
        lbl.setObjectName("PillOrange")
    else:
        lbl.setObjectName("PillRed")
    return lbl


def create_detection_crop_pixmap(label, size=76):
    """Generates a styled detection thumbnail with a bounding box graphic."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#1E232B"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(QColor("#33C9BB"), 2, Qt.DashLine)
    painter.setPen(pen)
    painter.drawRect(8, 8, size - 16, size - 16)

    icon_name = "face" if "Face" in label else "frame"
    icon = create_icon(icon_name, "#FFFFFF", 28)
    icon.paint(painter, size // 2 - 14, size // 2 - 14, 28, 28)

    painter.end()
    return pixmap


class TimelineWidget(QFrame):
    """A horizontal detection timeline showing the temporal distribution of detections.

    Each detection is rendered as a dot on a time axis from 00:00 to the video
    duration. Dots are clickable — clicking one selects that detection and
    updates the Detection Information Card above the queue.
    """

    detectionSelected = pyqtSignal(int)  # emits the detection's id

    def __init__(self, detections=None, duration_seconds=154, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(90)
        self.setCursor(Qt.PointingHandCursor)
        self._detections = detections or []
        self._duration = duration_seconds
        self._selected_id = None
        self._dot_positions = []  # [(x, y, id)]
        self.setStyleSheet("background-color: {bg}; border-radius: 12px;".format(
            bg=styles.PANEL_COLOR
        ))

    def set_selected_id(self, det_id):
        self._selected_id = det_id
        self.update()

    def _time_to_seconds(self, det):
        try:
            parts = det.get("time", "00:00:00").split(":")
            return int(parts[0]) * 60 + float(parts[1]) if len(parts) >= 2 else 0
        except (ValueError, IndexError):
            return 0

    def paintEvent(self, event):
        """Draw the timeline axis and detection markers."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin_x = 40
        axis_y = h - 25
        axis_start = margin_x
        axis_end = w - margin_x
        axis_width = axis_end - axis_start

        # Draw axis line
        axis_color = QColor(styles.BORDER_COLOR)
        painter.setPen(QPen(axis_color, 2))
        painter.drawLine(axis_start, axis_y, axis_end, axis_y)

        # Draw start/end labels
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        text_color = QColor(styles.MUTED_TEXT_COLOR)
        painter.setPen(text_color)
        painter.drawText(axis_start - 20, axis_y + 20, "00:00")
        end_min = self._duration // 60
        end_sec = self._duration % 60
        painter.drawText(axis_end - 25, axis_y + 20, f"{end_min:02d}:{end_sec:02d}")

        # Draw detection dots
        dot_radius = 8
        category_colors = {
            "FACE": QColor(styles.ACCENT_TEAL),
            "ID": QColor(styles.ACCENT_ORANGE),
            "DOCUMENT": QColor(styles.ACCENT_ORANGE),
            "SCREEN": QColor(styles.ACCENT_RED),
            "CREDENTIAL": QColor("#9B59B6"),
            "LICENSE_PLATE": QColor("#F39C12"),  # Gold color for license plates
        }

        self._dot_positions = []
        for det in self._detections:
            secs = self._time_to_seconds(det)
            ratio = min(1.0, secs / max(1, self._duration))
            x = axis_start + int(axis_width * ratio)
            y = axis_y
            self._dot_positions.append((x, y, det.get("id")))

            color = category_colors.get(det.get("category", "FACE"), QColor(styles.ACCENT_TEAL))
            is_selected = det.get("id") == self._selected_id

            # Draw outer selection ring
            if is_selected:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(color, 3))
                painter.drawEllipse(x - dot_radius - 6, y - dot_radius - 6,
                                    (dot_radius + 6) * 2, (dot_radius + 6) * 2)
            else:
                painter.setBrush(QColor(255, 255, 255, 30))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(x - dot_radius - 2, y - dot_radius - 2,
                                    (dot_radius + 2) * 2, (dot_radius + 2) * 2)

            # Draw dot
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            r = dot_radius + (2 if is_selected else 0)
            painter.drawEllipse(x - r, y - r, r * 2, r * 2)

            # Draw category label above
            label = det.get("category", "")
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(color)
            label_x = x - 20
            label_y = y - 15
            painter.drawText(label_x, label_y, label)

        painter.end()

    def mousePressEvent(self, event):
        """Select the detection whose dot is closest to the click, within a
        reasonable hit radius."""
        pos = event.pos()
        best_id, best_dist = None, 9999
        for x, y, det_id in self._dot_positions:
            dist = ((pos.x() - x) ** 2 + (pos.y() - y) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id = det_id
        if best_id is not None and best_dist <= 20:
            self.set_selected_id(best_id)
            self.detectionSelected.emit(best_id)
        super().mousePressEvent(event)


class ImagePreviewDialog(QDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{item['label']} - Frame {item['frame']} Preview")
        self.resize(540, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        image_lbl = QLabel()
        image_lbl.setAlignment(Qt.AlignCenter)
        image_lbl.setMinimumHeight(300)

        pixmap = load_scaled_pixmap(item["image_path"], 500, 300) if item.get("image_path") else None
        if pixmap is not None:
            image_lbl.setPixmap(pixmap)
        else:
            image_lbl.setPixmap(create_detection_crop_pixmap(item['label'], 200))
            styles.themed(image_lbl, lambda: f"background-color: {styles.BORDER_COLOR}; border-radius: 12px;")

        layout.addWidget(image_lbl)

        meta_lbl = QLabel(
            f"Source: {item['source']} | Frame: {item['frame']} | "
            f"Timestamp: {item.get('time', '00:00:00')} | "
            f"Confidence: {item['confidence'] * 100:.1f}%"
        )
        styles.themed(meta_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        layout.addWidget(meta_lbl)

        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close Preview")
        close_btn.setObjectName("SecondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class DetectionInfoCard(QFrame):
    """Detailed information card shown when a detection is selected from the
    timeline or the queue. Displays Class, Confidence, Frame, OCR Text,
    Classification, and Classification Confidence, plus Previous / Confirm
    Redaction / Next controls to move through the queue.
    """

    previousRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    confirmRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._item = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon("review", styles.ACCENT_TEAL, 20).pixmap(20, 20))
        header_row.addWidget(icon_lbl)
        title_lbl = QLabel("Detection Details")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        self.status_pill_holder = QHBoxLayout()
        header_row.addLayout(self.status_pill_holder)
        outer.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(20)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(96, 96)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        styles.themed(self.thumb_lbl, lambda: f"background-color: {styles.BORDER_COLOR}; border-radius: 10px;")
        body_row.addWidget(self.thumb_lbl)

        fields_col = QVBoxLayout()
        fields_col.setSpacing(6)
        self.field_labels = {}
        for key, title in [
            ("class", "Class"),
            ("confidence", "Confidence"),
            ("frame", "Frame"),
            ("ocr_text", "OCR Text"),
            ("classification", "Classification"),
            ("classification_confidence", "Confidence Score"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            key_lbl = QLabel(f"{title}:")
            key_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")
            key_lbl.setFixedWidth(150)
            val_lbl = QLabel("\u2014")
            val_lbl.setWordWrap(True)
            styles.themed(val_lbl, lambda: f"color: {styles.TEXT_COLOR}; font-size: 13px;")
            row.addWidget(key_lbl)
            row.addWidget(val_lbl, 1)
            fields_col.addLayout(row)
            self.field_labels[key] = val_lbl

        body_row.addLayout(fields_col, 1)
        outer.addLayout(body_row)

        # Review controls: Previous / Confirm Redaction / Next
        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        self.prev_btn = QPushButton("  Previous")
        self.prev_btn.setObjectName("SecondaryButton")
        self.prev_btn.setIcon(create_icon("chevron_left", styles.ACCENT_TEAL, 16))
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setFixedHeight(40)
        self.prev_btn.clicked.connect(self.previousRequested.emit)
        controls_row.addWidget(self.prev_btn)

        self.confirm_btn = QPushButton("  Confirm Redaction")
        self.confirm_btn.setObjectName("PrimaryButton")
        self.confirm_btn.setIcon(create_icon("check", "#FFFFFF", 16))
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.clicked.connect(self.confirmRequested.emit)
        controls_row.addWidget(self.confirm_btn)

        self.next_btn = QPushButton("Next  ")
        self.next_btn.setObjectName("SecondaryButton")
        self.next_btn.setLayoutDirection(Qt.RightToLeft)
        self.next_btn.setIcon(create_icon("chevron_right", styles.ACCENT_TEAL, 16))
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setFixedHeight(40)
        self.next_btn.clicked.connect(self.nextRequested.emit)
        controls_row.addWidget(self.next_btn)

        controls_row.addStretch()
        outer.addLayout(controls_row)

    def set_item(self, item):
        """Populate the card from a detection dict, or clear it if None."""
        self._item = item
        while self.status_pill_holder.count():
            child = self.status_pill_holder.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if item is None:
            for lbl in self.field_labels.values():
                lbl.setText("\u2014")
            self.thumb_lbl.clear()
            self.confirm_btn.setEnabled(False)
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        pill = status_pill(item.get("status", "pending"))
        self.status_pill_holder.addWidget(pill)

        pixmap = (load_scaled_pixmap(item["image_path"], 96, 96) if item.get("image_path")
                  else create_detection_crop_pixmap(item["label"], 96))
        self.thumb_lbl.setPixmap(pixmap)

        self.field_labels["class"].setText(item.get("label", "\u2014"))
        self.field_labels["confidence"].setText(f"{item['confidence'] * 100:.1f}%")
        frame_number = item.get("frame", "—")
        self.field_labels["frame"].setText(f"{frame_number}  ({item.get('time', '00:00:00')})")
        ocr = item.get("ocr_text")
        self.field_labels["ocr_text"].setText(ocr if ocr else "Not available")
        self.field_labels["classification"].setText(item.get("classification") or "\u2014")
        cls_conf = item.get("classification_confidence")
        self.field_labels["classification_confidence"].setText(
            f"{cls_conf * 100:.1f}%" if cls_conf is not None else "\u2014"
        )

        status = item.get("status")
        is_pending = status == "pending"
        self.confirm_btn.setEnabled(is_pending)
        if status == "confirmed":
            self.confirm_btn.setText("  Redaction Confirmed")
        elif status == "rejected":
            self.confirm_btn.setText("  Rejected \u2014 Not Redacted")
        else:
            self.confirm_btn.setText("  Confirm Redaction")
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

    def retheme(self):
        self.thumb_lbl.setStyleSheet(f"background-color: {styles.BORDER_COLOR}; border-radius: 10px;")
        self.confirm_btn.setIcon(create_icon("check", "#FFFFFF", 16))
        self.prev_btn.setIcon(create_icon("chevron_left", styles.CURRENT_COLORS["ACCENT_TEAL"], 16))
        self.next_btn.setIcon(create_icon("chevron_right", styles.CURRENT_COLORS["ACCENT_TEAL"], 16))
        if self._item is not None:
            self.set_item(self._item)


class ReviewItemCard(QFrame):
    """Detection card showing type, timestamp, confidence, action, and status."""
    def __init__(self, item, on_decision, on_select, is_selected=False):
        super().__init__()
        self.setObjectName("SelectableCard")
        self.item = item
        self.on_decision = on_decision
        self.on_select = on_select
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("selected", is_selected)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        # Thumbnail
        thumb = QPushButton()
        thumb.setFixedSize(76, 76)
        thumb.setCursor(Qt.PointingHandCursor)
        thumb.setToolTip("Click to view detection preview")
        thumb.clicked.connect(self.show_preview)

        pixmap = (load_scaled_pixmap(item["image_path"], 76, 76) if item.get("image_path")
                  else create_detection_crop_pixmap(item['label'], 76))
        thumb.setIcon(QIcon(pixmap))
        thumb.setIconSize(pixmap.size())
        styles.themed(thumb, lambda: "border: none; border-radius: 10px;")
        layout.addWidget(thumb)

        # Detection Details
        details = QVBoxLayout()
        details.setSpacing(6)

        # Title row with type and timestamp
        title_row = QHBoxLayout()
        icon_name = "face" if "Face" in item["label"] else "review"
        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 18).pixmap(18, 18))
        title_lbl = QLabel(item["label"])
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        # Status badge — Pending Review / Confirmed / Rejected
        title_row.addWidget(status_pill(item.get("status", "pending")))
        details.addLayout(title_row)

        # Timestamp + confidence
        info_row = QHBoxLayout()
        info_row.setSpacing(20)

        frame_number = item.get("frame", "—")
        ts_lbl = QLabel(f"Frame {frame_number}  ·  {item.get('time', '00:00:00')}")
        info_row.addWidget(ts_lbl)
        info_row.addWidget(confidence_pill(item["confidence"]))
        info_row.addStretch()
        details.addLayout(info_row)

        layout.addLayout(details, 1)

        # Action Buttons
        actions = QVBoxLayout()
        actions.setSpacing(8)

        confirm_btn = QPushButton("  Confirm")
        confirm_btn.setObjectName("PrimaryButton")
        confirm_btn.setIcon(create_icon("check", "#FFFFFF", 14))
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setToolTip("Confirm this detection for redaction")
        confirm_btn.setEnabled(item.get("status") == "pending")
        confirm_btn.clicked.connect(lambda: self.on_decision(self.item, "confirmed"))

        discard_btn = QPushButton("Reject")
        discard_btn.setObjectName("SecondaryButton")
        discard_btn.setCursor(Qt.PointingHandCursor)
        discard_btn.setToolTip("Mark as not required \u2014 leave unredacted")
        discard_btn.setEnabled(item.get("status") == "pending")
        discard_btn.clicked.connect(lambda: self.on_decision(self.item, "rejected"))

        actions.addWidget(confirm_btn)
        actions.addWidget(discard_btn)
        layout.addLayout(actions)

    def mousePressEvent(self, event):
        self.on_select(self.item.get("id"))
        super().mousePressEvent(event)

    def show_preview(self):
        ImagePreviewDialog(self.item, self).exec_()


class ReviewPage(QWidget):
    """Detection review page with timeline, detail card, and item cards.

    Populated for real via set_detections(), called by MainWindow after a
    processing job completes (see main.py's _handle_processing_complete)
    or by a live session's confidence-gated review queue.
    """
    def __init__(self, backend=None):
        super().__init__()
        # Starts empty — this used to default to MOCK_QUEUE, showing fake
        # detections as if they were real results before any video had
        # ever been processed (the same bug fixed in Results.py).
        self.queue = []
        self.selected_id = None
        self._navigate_callback = None
        # Optional: when set, a "Confirm" decision here also feeds the
        # active-learning dataset (see ActiveLearningStore), the same as
        # the FastAPI /review/{id}/decision endpoint already does. None
        # is fine — file-processing results still show and can be
        # reviewed either way, this only affects whether confirmations
        # grow the training set.
        self._backend = backend

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(18)

        # Header
        header_section = QVBoxLayout()
        header_section.setSpacing(4)

        header_row = QHBoxLayout()
        self.heading_lbl = QLabel(f"Review Queue \u2014 {len(self.queue)} Items")
        self.heading_lbl.setObjectName("PageTitle")
        self.count_badge = QLabel("0 Pending")
        self.count_badge.setObjectName("PillOrange")
        header_row.addWidget(self.heading_lbl)
        header_row.addStretch()
        header_row.addWidget(self.count_badge)
        header_section.addLayout(header_row)

        desc = QLabel(
            "Detections that fall between the low and high confidence thresholds "
            "appear here. Select a detection on the timeline or a card below to "
            "see its full details, then Confirm Redaction, Reject, or step through "
            "with Previous / Next."
        )
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        header_section.addWidget(desc)
        main_layout.addLayout(header_section)

        # Timeline
        timeline_label = QLabel("Detection Timeline")
        timeline_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        main_layout.addWidget(timeline_label)

        self.timeline = TimelineWidget(self.queue)
        self.timeline.detectionSelected.connect(self.select_detection)
        main_layout.addWidget(self.timeline)

        # Detection Information Card
        detail_label = QLabel("Detection Details")
        detail_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        main_layout.addWidget(detail_label)

        self.detail_card = DetectionInfoCard()
        self.detail_card.previousRequested.connect(self.go_previous)
        self.detail_card.nextRequested.connect(self.go_next)
        self.detail_card.confirmRequested.connect(self.confirm_selected)
        main_layout.addWidget(self.detail_card)

        # Queue
        queue_label = QLabel("All Detections")
        queue_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        main_layout.addWidget(queue_label)

        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(12)
        main_layout.addWidget(self.queue_container)

        # Empty state widget
        self.empty_state = EmptyState(
            title="No detections to review",
            description="Processed privacy events will appear here after a video has been processed.",
            icon_name="review"
        )
        self.empty_state.hide()
        main_layout.addWidget(self.empty_state)

        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

        self.refresh()

    # -- Selection / navigation --------------------------------------

    def _selected_index(self):
        for i, item in enumerate(self.queue):
            if item["id"] == self.selected_id:
                return i
        return -1

    def select_detection(self, det_id):
        self.selected_id = det_id
        self.refresh(rebuild_cards=True)

    def go_previous(self):
        if not self.queue:
            return
        idx = self._selected_index()
        idx = (idx - 1) % len(self.queue) if idx >= 0 else 0
        self.selected_id = self.queue[idx]["id"]
        self.refresh(rebuild_cards=True)

    def go_next(self):
        if not self.queue:
            return
        idx = self._selected_index()
        idx = (idx + 1) % len(self.queue) if idx >= 0 else 0
        self.selected_id = self.queue[idx]["id"]
        self.refresh(rebuild_cards=True)

    def confirm_selected(self):
        idx = self._selected_index()
        if idx < 0:
            return
        self.handle_decision(self.queue[idx], "confirmed")

    # -- Data / rendering ----------------------------------------------

    def refresh(self, rebuild_cards=True):
        """Rebuild the queue UI from self.queue data."""
        pending_count = sum(1 for i in self.queue if i.get("status") == "pending")
        self.heading_lbl.setText(f"Review Queue \u2014 {len(self.queue)} Items")
        self.count_badge.setText(f"{pending_count} Pending")

        if not self.queue:
            self.queue_container.hide()
            self.timeline.hide()
            self.detail_card.hide()
            self.empty_state.show()
            self.detail_card.set_item(None)
            return

        self.empty_state.hide()
        self.queue_container.show()
        self.timeline.show()
        self.detail_card.show()

        if self.selected_id is None or self._selected_index() < 0:
            self.selected_id = self.queue[0]["id"]

        self.timeline._detections = self.queue
        self.timeline.set_selected_id(self.selected_id)

        if rebuild_cards:
            while self.queue_layout.count():
                child = self.queue_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            for item in self.queue:
                card = ReviewItemCard(
                    item, self.handle_decision, self.select_detection,
                    is_selected=(item["id"] == self.selected_id)
                )
                self.queue_layout.addWidget(card)

        idx = self._selected_index()
        self.detail_card.set_item(self.queue[idx] if idx >= 0 else None)

    def handle_decision(self, item, decision):
        """Set a detection's state to 'confirmed' or 'rejected'. Detections
        stay visible in the queue with their new state rather than being
        removed, per the Pending Review / Confirmed / Rejected model."""
        for i in self.queue:
            if i["id"] == item["id"]:
                i["status"] = decision
                if self._backend is not None:
                    # Correction feedback mechanism: every decision (not
                    # just confirmations) is logged, so refine_classifier()
                    # can later learn which rule patterns reviewers
                    # actually agree with — no retraining involved.
                    try:
                        self._backend.correction_log.log_decision(
                            i["id"], i.get("category"), i.get("classification"), decision
                        )
                    except Exception:
                        pass  # never let logging break the review UI
                if decision == "confirmed" and self._backend is not None:
                    # A confirmed detection is a human-verified label for
                    # exactly the input the model was uncertain about (that's
                    # why it reached review at all) — feed it into the
                    # training dataset instead of discarding it once the
                    # redaction decision is made. No-ops quietly if this
                    # item has no saved frame image (see ProcessingPipeline).
                    try:
                        self._backend.active_learning.record_confirmed_dict(i)
                    except Exception:
                        pass  # never let dataset bookkeeping break the review UI
                break
        self.refresh(rebuild_cards=True)

    def set_detections(self, detections):
        """Public API: replace the queue with new detections from the backend."""
        self.queue = list(detections)
        self.selected_id = self.queue[0]["id"] if self.queue else None
        self.refresh()

    def clear_detections(self):
        """Public API: clear the queue."""
        self.queue = []
        self.selected_id = None
        self.refresh()

    def reset(self):
        """Public API: clear the review session (used by Results' 'Process
        Another Video' action)."""
        self.clear_detections()

    def retheme(self):
        retheme_widget_tree(self)
        # Refresh the reusable state components
        if hasattr(self, 'empty_state'):
            self.empty_state.retheme()
        if hasattr(self, 'detail_card'):
            self.detail_card.retheme()
        self.refresh()
