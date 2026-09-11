# Results.py
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QGridLayout, QStackedWidget, QFileDialog)
from PyQt5.QtCore import Qt
import styles
from components import (create_icon, retheme_widget_tree, NotificationBanner,
                        create_scrollable_container, EmptyState)


class ResultMetricCard(QFrame):
    """A compact metric card used in the results summary grid."""
    def __init__(self, title, value, subtitle=None, icon_name="results"):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        title_lbl = QLabel(title)
        styles.themed(title_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 600;")
        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 18).pixmap(18, 18))
        icon_lbl._retheme_icon = lambda: icon_lbl.setPixmap(
            create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 18).pixmap(18, 18))

        top_row.addWidget(title_lbl)
        top_row.addStretch()
        top_row.addWidget(icon_lbl)
        layout.addLayout(top_row)

        value_lbl = QLabel(str(value))
        styles.themed(value_lbl, lambda: f"font-size: 24px; font-weight: bold; color: {styles.TEXT_COLOR};")
        layout.addWidget(value_lbl)
        self.value_lbl = value_lbl  # exposed so set_results()/summary refresh can update it

        if subtitle:
            sub_lbl = QLabel(subtitle)
            styles.themed(sub_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 11px;")
            layout.addWidget(sub_lbl)


class CategoryCountCard(QFrame):
    """Card displaying a single category count."""
    def __init__(self, category_name, count, icon_name):
        super().__init__()
        self.setObjectName("Card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 20).pixmap(20, 20))
        icon_lbl._retheme_icon = lambda: icon_lbl.setPixmap(
            create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 20).pixmap(20, 20))
        layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)
        name_lbl = QLabel(category_name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        text_layout.addWidget(name_lbl)

        self._count_lbl = QLabel(str(count))
        styles.themed(self._count_lbl, lambda: f"color: {styles.ACCENT_TEAL}; font-size: 16px; font-weight: bold;")
        text_layout.addWidget(self._count_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_count(self, count):
        self._count_lbl.setText(str(count))


class ResultsPage(QWidget):
    """Professional results summary page.

    Frontend-only. The set_results() method is the public API for the future
    backend to populate results data.
    """
    def __init__(self, navigate_callback, reset_session_callback=None):
        super().__init__()
        self.navigate = navigate_callback
        # Called by "Process Another Video" to clear the Process/Review
        # session state elsewhere in the app and return Home. Falls back to
        # a plain Home navigation if the app didn't wire one up.
        self.reset_session_callback = reset_session_callback
        self._exporting = False

        # Zeroed until set_results() is called with a real completed job.
        self._video_duration = "00:00"
        self._processing_time = "00:00"
        self._frames_processed = "0"
        self._total_redactions = "0"
        self._category_counts = {
            "Faces": 0,
            "Credentials": 0,
            "Documents": 0,
            "Screens": 0,
            "Other": 0,
        }
        # Processing Summary metrics — all zeroed until a real job finishes;
        # these used to be hard-coded sample numbers (0.952 precision, 128
        # detections, ...) shown as if they were real results before any
        # video had ever been processed.
        self._summary = {
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "avg_fps": 0.0,
            "total_detections": 0,
            "auto_redacted": 0,
            "temporal_iou": 0.0,
        }
        self._category_counts = {k: 0 for k in self._category_counts}
        self._output_path = None
        self._has_results = False  # No results exist until set_results() is called with real data

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(0, 0, 10, 20)
        main_layout.setSpacing(20)

        # Header
        header_section = QVBoxLayout()
        header_section.setSpacing(4)
        title = QLabel("Results")
        title.setObjectName("PageTitle")
        desc = QLabel("Summary of the most recent processing job. Click a category for details.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        header_section.addWidget(title)
        header_section.addWidget(desc)
        main_layout.addLayout(header_section)

        # Content container (will hold either results or empty state)
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)

        # --- Page 0: Results content ---
        self.results_widget = QWidget()
        results_layout = QVBoxLayout(self.results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(20)

        # Completion banner
        completion_card = QFrame()
        completion_card.setObjectName("Card")
        completion_layout = QHBoxLayout(completion_card)
        completion_layout.setContentsMargins(20, 16, 20, 16)
        completion_layout.setSpacing(12)

        check_icon = QLabel()
        check_icon.setPixmap(create_icon("check_circle", styles.ACCENT_TEAL, 28).pixmap(28, 28))
        completion_layout.addWidget(check_icon)

        completion_text_layout = QVBoxLayout()
        completion_text_layout.setSpacing(2)
        completion_title = QLabel("Processing Complete")
        completion_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        completion_text_layout.addWidget(completion_title)
        completion_sub = QLabel("Your video has been successfully redacted and saved.")
        styles.themed(completion_sub, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px;")
        completion_text_layout.addWidget(completion_sub)
        completion_layout.addLayout(completion_text_layout, 1)
        results_layout.addWidget(completion_card)

        # Primary metrics grid
        metrics_label = QLabel("Overview")
        metrics_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        main_layout.addWidget(metrics_label)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(14)

        self.card_duration = ResultMetricCard("Video Duration", self._video_duration, "Source clip length", "video")
        self.card_time = ResultMetricCard("Processing Time", self._processing_time, "Total pipeline runtime", "speed")
        self.card_frames = ResultMetricCard("Frames Processed", self._frames_processed, "Avg. 41.5 FPS", "frame")
        self.card_redactions = ResultMetricCard("Total Redactions", self._total_redactions, "Across all categories", "shield")

        metrics_grid.addWidget(self.card_duration, 0, 0)
        metrics_grid.addWidget(self.card_time, 0, 1)
        metrics_grid.addWidget(self.card_frames, 1, 0)
        metrics_grid.addWidget(self.card_redactions, 1, 1)

        results_layout.addLayout(metrics_grid)

        # Processing Summary
        summary_label = QLabel("Processing Summary")
        summary_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        results_layout.addWidget(summary_label)

        summary_grid = QGridLayout()
        summary_grid.setSpacing(14)

        self.card_precision = ResultMetricCard("Precision", "0.0%", icon_name="detect")
        self.card_recall = ResultMetricCard("Recall", "0.0%", icon_name="detect")
        self.card_f1 = ResultMetricCard("F1-score", "0.0%", icon_name="detect")
        self.card_avg_fps = ResultMetricCard("Average FPS", "0.0", icon_name="speed")
        self.card_total_detections = ResultMetricCard("Total Detections", "0", icon_name="review")
        self.card_auto_redacted = ResultMetricCard("Auto-Redacted", "0", icon_name="shield")
        self.card_temporal_iou = ResultMetricCard("Temporal IoU", "0.0%", icon_name="frame")

        summary_grid.addWidget(self.card_precision, 0, 0)
        summary_grid.addWidget(self.card_recall, 0, 1)
        summary_grid.addWidget(self.card_f1, 0, 2)
        summary_grid.addWidget(self.card_avg_fps, 1, 0)
        summary_grid.addWidget(self.card_total_detections, 1, 1)
        summary_grid.addWidget(self.card_auto_redacted, 1, 2)
        summary_grid.addWidget(self.card_temporal_iou, 2, 0, 1, 3)

        results_layout.addLayout(summary_grid)
        self._refresh_summary_cards()

        # Category counts
        categories_label = QLabel("Detections by Category")
        categories_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        results_layout.addWidget(categories_label)

        categories_row = QHBoxLayout()
        categories_row.setSpacing(12)
        self._cat_cards = {
            "Faces": CategoryCountCard("Faces", self._category_counts["Faces"], "face"),
            "Credentials": CategoryCountCard("Credentials", self._category_counts["Credentials"], "shield"),
            "Documents": CategoryCountCard("Documents", self._category_counts["Documents"], "frame"),
            "Screens": CategoryCountCard("Screens", self._category_counts["Screens"], "video"),
            "Other": CategoryCountCard("Other", self._category_counts["Other"], "flag"),
        }
        for card in self._cat_cards.values():
            categories_row.addWidget(card, 1)
        results_layout.addLayout(categories_row)

        # Notification banner for status feedback
        self.banner = NotificationBanner()
        results_layout.addWidget(self.banner)

        # Action buttons
        actions_label = QLabel("Actions")
        actions_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        results_layout.addWidget(actions_label)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        open_btn = QPushButton("  Open Output")
        open_btn.setObjectName("PrimaryButton")
        open_btn.setIcon(create_icon("play", "#FFFFFF", 16))
        open_btn.setFixedHeight(44)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_output)

        review_btn = QPushButton("  Review Detections")
        review_btn.setObjectName("SecondaryButton")
        review_btn.setIcon(create_icon("review", styles.ACCENT_TEAL, 16))
        review_btn.setFixedHeight(44)
        review_btn.setCursor(Qt.PointingHandCursor)
        review_btn.clicked.connect(lambda: self.navigate("Review"))

        export_btn = QPushButton("  Export Report")
        export_btn.setObjectName("SecondaryButton")
        export_btn.setIcon(create_icon("export", styles.ACCENT_TEAL, 16))
        export_btn.setFixedHeight(44)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self.export_output)

        self.export_video_btn = QPushButton("  \U0001F3AC Export MP4")
        self.export_video_btn.setObjectName("SecondaryButton")
        self.export_video_btn.setIcon(create_icon("video", styles.ACCENT_TEAL, 16))
        self.export_video_btn.setFixedHeight(44)
        self.export_video_btn.setCursor(Qt.PointingHandCursor)
        self.export_video_btn.setToolTip("Export the redacted video as an MP4 file")
        self.export_video_btn.clicked.connect(self.export_video)

        actions_row.addWidget(open_btn)
        actions_row.addWidget(review_btn)
        actions_row.addWidget(export_btn)
        actions_row.addWidget(self.export_video_btn)
        actions_row.addStretch()
        results_layout.addLayout(actions_row)

        # Process Another Video — prominent, resets the session and returns Home
        another_row = QHBoxLayout()
        self.process_another_btn = QPushButton("  Process Another Video")
        self.process_another_btn.setObjectName("PrimaryButton")
        self.process_another_btn.setIcon(create_icon("video", "#FFFFFF", 18))
        self.process_another_btn.setFixedHeight(48)
        self.process_another_btn.setCursor(Qt.PointingHandCursor)
        self.process_another_btn.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.process_another_btn.clicked.connect(self.process_another_video)
        another_row.addWidget(self.process_another_btn)
        another_row.addStretch()
        results_layout.addLayout(another_row)

        results_layout.addStretch()

        # --- Page 1: Empty state ---
        self.empty_state = EmptyState(
            title="No Results Available",
            description="Process a video to see redaction results here.",
            icon_name="results"
        )

        self.content_stack.addWidget(self.results_widget)
        self.content_stack.addWidget(self.empty_state)

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

    def open_output(self):
        if not self._output_path or not os.path.exists(self._output_path):
            self.banner.show_message("No redacted output file yet — process a video first.", "warning")
            return
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_path))

    def export_output(self):
        """Export a text summary report of the results — the JSON/text
        breakdown (categories, counts, timing), distinct from
        export_video() which exports the redacted video file itself.
        Previously this just called export_video() again, so "Export
        Report" and "Export MP4" silently did the exact same thing and no
        report ever existed.
        """
        if not self._has_results:
            self.banner.show_message("No results to export yet — process a video first.", "warning")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Report", "privarcy_report.txt", "Text Report (*.txt);;JSON Report (*.json)"
        )
        if not path:
            return

        report = {
            "video_duration": self._video_duration,
            "processing_time": self._processing_time,
            "frames_processed": self._frames_processed,
            "total_redactions": self._total_redactions,
            "categories": dict(self._category_counts),
            "summary": self._summary,
            "output_video": self._output_path,
        }
        try:
            if path.lower().endswith(".json"):
                import json
                content = json.dumps(report, indent=2)
            else:
                lines = [
                    "PrivARcy Processing Report", "=" * 27, "",
                    f"Video duration:      {report['video_duration']}",
                    f"Processing time:     {report['processing_time']}",
                    f"Frames processed:    {report['frames_processed']}",
                    f"Total redactions:    {report['total_redactions']}",
                    "", "Detections by category:",
                ]
                lines += [f"  {name:<14} {count}" for name, count in report["categories"].items()]
                lines += ["", "Summary:"]
                lines += [f"  {key}: {value}" for key, value in report["summary"].items()]
                if report["output_video"]:
                    lines += ["", f"Redacted video: {report['output_video']}"]
                content = "\n".join(lines)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.banner.show_message(f"Report exported to {os.path.basename(path)}.", "success")
        except OSError as exc:
            self.banner.show_message(f"Could not write {os.path.basename(path)}: {exc}", "error")

    def _refresh_summary_cards(self):
        s = self._summary
        self.card_precision.value_lbl.setText(f"{s['precision'] * 100:.1f}%")
        self.card_recall.value_lbl.setText(f"{s['recall'] * 100:.1f}%")
        self.card_f1.value_lbl.setText(f"{s['f1_score'] * 100:.1f}%")
        self.card_avg_fps.value_lbl.setText(f"{s['avg_fps']:.1f}")
        self.card_total_detections.value_lbl.setText(f"{s['total_detections']:,}")
        self.card_auto_redacted.value_lbl.setText(f"{s['auto_redacted']:,}")
        self.card_temporal_iou.value_lbl.setText(f"{s['temporal_iou'] * 100:.1f}%")

    def export_video(self):
        """Export the processed/redacted video as an MP4 file.

        Copies the real file the pipeline already wrote to
        `AppConfig.output_dir` (set via `set_results({"output_path": ...})`)
        to wherever the user chooses. No fake "preparing" delay and no
        placeholder failure message — either the file exists and gets
        copied, or the user gets a real, specific error.
        """
        if self._exporting:
            return
        if not self._output_path or not os.path.exists(self._output_path):
            self.banner.show_message(
                "No redacted output file available yet — process a video first.", "warning"
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Redacted Video", "redacted_output.mp4", "MP4 Video (*.mp4)"
        )
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"

        self._exporting = True
        self.export_video_btn.setEnabled(False)
        self.export_video_btn.setText("  Exporting...")
        try:
            import shutil
            shutil.copyfile(self._output_path, path)
            self.export_video_result(success=True, message=f"Exported to {os.path.basename(path)}.")
        except OSError as exc:
            self.export_video_result(success=False, message=f"Could not write {os.path.basename(path)}: {exc}")

    def export_video_result(self, success, message=None):
        """Public API: called once the export finishes (or fails) to
        update the button/banner state."""
        self._exporting = False
        self.export_video_btn.setEnabled(True)
        self.export_video_btn.setText("  \U0001F3AC Export MP4")
        if success:
            self.banner.show_message(message or "Video exported successfully.", "success")
        else:
            self.banner.show_message(message or "Video export failed.", "error")

    def process_another_video(self):
        """Reset the current session and return to Home so a new video can
        be selected and processed, per the Results \u2192 Process Another
        Video \u2192 Reset \u2192 Home flow."""
        self._has_results = False
        self.content_stack.setCurrentIndex(1)
        if self.reset_session_callback:
            self.reset_session_callback()
        else:
            self.navigate("Home")

    def reset(self):
        """Public API: clear this page's results state (used alongside
        Process/Review resets when starting a new session)."""
        self._has_results = False
        self.content_stack.setCurrentIndex(1)
        self.banner.hide()
        self._exporting = False
        self.export_video_btn.setEnabled(True)
        self.export_video_btn.setText("  \U0001F3AC Export MP4")

        # Zero the category cards and summary — otherwise a bucket with no
        # detections in the new video (so it's absent from the next
        # set_results() call's "categories" dict) would keep showing the
        # previous video's stale count.
        self._summary = {k: 0.0 for k in self._summary}
        self._category_counts = {k: 0 for k in self._category_counts}
        for name, card in self._cat_cards.items():
            card.set_count(0)
        self._video_duration = "00:00"
        self._processing_time = "00:00"
        self._frames_processed = "0"
        self._total_redactions = "0"
        self._output_path = None

    def set_results(self, results):
        """Public API: replace results data from the backend.

        Expected shape:
        {
            "video_duration": "02:43",
            "processing_time": "01:37",
            "frames_processed": "10,842",
            "total_redactions": "54",
            "categories": {"Faces": 32, "Credentials": 12, ...},
            "summary": {
                "precision": 0.95, "recall": 0.94, "f1_score": 0.94,
                "avg_fps": 30.4, "total_detections": 128,
                "auto_redacted": 115, "temporal_iou": 0.92,
            },
        }
        """
        has_data = bool(results and (results.get("total_redactions", 0) or 
                                     any(results.get("categories", {}).values())))
        self._has_results = has_data
        
        if has_data:
            if "video_duration" in results:
                self._video_duration = results["video_duration"]
                self.card_duration.value_lbl.setText(self._video_duration)
            if "processing_time" in results:
                self._processing_time = results["processing_time"]
            if "frames_processed" in results:
                self._frames_processed = str(results["frames_processed"])
                self.card_frames.value_lbl.setText(self._frames_processed)
            if "total_redactions" in results:
                self._total_redactions = str(results["total_redactions"])
                self.card_redactions.value_lbl.setText(self._total_redactions)
            if "output_path" in results:
                self._output_path = results["output_path"]
            if "categories" in results:
                # Treat this as the full breakdown for the video just
                # processed, not a partial update — a bucket with zero
                # detections legitimately won't be a key in this dict, but
                # its card must still show 0, not whatever the previous
                # video left behind.
                for name in self._cat_cards:
                    count = results["categories"].get(name, 0)
                    self._cat_cards[name].set_count(count)
                    self._category_counts[name] = count
            if "summary" in results:
                self._summary.update(results["summary"])
                self._refresh_summary_cards()
        
        # Switch between results view and empty state
        self.content_stack.setCurrentIndex(0 if has_data else 1)

    def retheme(self):
        retheme_widget_tree(self)
        # Refresh the empty state component
        if hasattr(self, 'empty_state'):
            self.empty_state.retheme()
        if hasattr(self, 'export_video_btn'):
            self.export_video_btn.setIcon(create_icon("video", styles.CURRENT_COLORS['ACCENT_TEAL'], 16))
        if hasattr(self, 'process_another_btn'):
            self.process_another_btn.setIcon(create_icon("video", "#FFFFFF", 18))
