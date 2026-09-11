# components.py
import os
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QGraphicsDropShadowEffect, QWidget, QScrollArea,
                             QPushButton)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPixmap, QPainter, QIcon, QPen, QBrush, QFont, QLinearGradient
from PyQt5.QtSvg import QSvgRenderer
import styles


def retheme_widget_tree(root):
    """Walk `root` and everything under it, re-applying any inline
    stylesheet registered via styles.themed() and refreshing any icon
    pixmap registered via `_retheme_icon`. This is how pages pick up a
    new light/dark palette without being torn down and rebuilt."""
    candidates = [root] + root.findChildren(QWidget)
    for w in candidates:
        fn = getattr(w, "_theme_style_fn", None)
        if fn is not None:
            w.setStyleSheet(fn())
        icon_fn = getattr(w, "_retheme_icon", None)
        if callable(icon_fn):
            icon_fn()


def create_icon(icon_name, color, size=20):
    """Generates modern SVG icons using the standard QtSvg module."""
    svg_paths = {
        "home": "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
        "process": "M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z",
        "face": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z",
        "review": "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-4-4 1.41-1.41L12 14.17l6.59-6.59L20 9l-8 8z",
        "live": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm0-13c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zm0 8c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3z",
        "results": "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z",
        "settings": "M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z",
        "shield": "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z",
        "privacy": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8 0-1.85.63-3.55 1.69-4.9L16.9 18.31C15.55 19.37 13.85 20 12 20zm6.31-3.1L7.1 5.69C8.45 4.63 10.15 4 12 4c4.41 0 8 3.59 8 8 0 1.85-.63 3.55-1.69 4.9z",
        "check": "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
        "check_circle": "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
        "close": "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
        "trash": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
        "eye": "M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z",
        "video": "M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z",
        "webcam": "M12 2c-4.42 0-8 3.58-8 8 0 3.82 2.67 7.02 6.25 7.82V20H8v2h8v-2h-2.25v-2.18c3.58-.8 6.25-4 6.25-7.82 0-4.42-3.58-8-8-8zm0 12c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
        "mobile": "M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z",
        "speed": "M20.38 8.57l-1.23 1.85a8 8 0 0 1-.22 7.58H5.07A8 8 0 0 1 15.58 6.85l1.85-1.23A10 10 0 0 0 3.35 19a2 2 0 0 0 1.72 1h13.85a2 2 0 0 0 1.74-1 10 10 0 0 0-.28-10.43zM10.59 15.41a2 2 0 0 0 2.83 0l5.66-8.49-8.49 5.66a2 2 0 0 0 0 2.83z",
        "detect": "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 17.93V18a1 1 0 0 0-2 0v1.93A8 8 0 0 1 4.07 13H6a1 1 0 0 0 0-2H4.07A8 8 0 0 1 11 4.07V6a1 1 0 0 0 2 0V4.07A8 8 0 0 1 19.93 11H18a1 1 0 0 0 0 2h1.93A8 8 0 0 1 13 19.93z",
        "flag": "M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z",
        "frame": "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z",
        "save": "M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z",
        "export": "M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z",
        "slider": "M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z",
        "blur": "M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z",
        "mask": "M3 5h18v14H3V5zm2 2v10h14V7H5z",
        "avatar": "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
        "play": "M8 5v14l11-7z",
        "quit": "M10.09 15.59L11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3H5c-1.11 0-2 .9-2 2v4h2V5h14v14H5v-4H3v4c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z",
        "power": "M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.38 1.19-4.47 3-5.74L6.58 4.84A8.99 8.99 0 0 0 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z",
        "chevron_left": "M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z",
        "chevron_right": "M8.59 16.59L10 18l6-6-6-6-1.41 1.41L13.17 12z",
        "document": "M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z",
        "card": "M20 4H4c-1.11 0-2 .89-2 2v12c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z",
        "text": "M5 4v3h5.5v12h3V7H19V4z",
        # Camera flip/mirror — two curved arrows chasing each other, the
        # standard "flip horizontal" glyph. Previously Live.py's Flip
        # Camera button asked for a nonexistent "shuffle" icon and
        # silently fell back to the gear/settings icon.
        "flip": "M15.55 5.55L11 1v3.07C7.06 4.56 4 7.92 4 12s3.05 7.44 7 7.93v-2.02c-2.84-.48-5-2.94-5-5.91s2.16-5.43 5-5.91V10l4.55-4.45zM19.94 13c-.14 1.55-.71 2.98-1.6 4.19l1.42 1.42A9.98 9.98 0 0021.94 13h-2zM13 19.93v2.02a9.98 9.98 0 006.31-2.98l-1.42-1.42c-1.2.9-2.62 1.46-4.16 1.66l-.73.72zM6.06 6.61L4.64 5.19A9.98 9.98 0 002.06 11h2c.14-1.55.71-2.98 1.6-4.19l.4-.2z",
        # Clock/history — used for the processing-history / recent-
        # activity feed.
        "history": "M13 3a9 9 0 00-9 9H1l3.89 3.89.07.14L9 12H6a7 7 0 117 7 6.9 6.9 0 01-4.95-2.05l-1.41 1.41A9 9 0 1013 3zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z",
        # Face scan + liveness — an eye-shaped scan reticle, distinct from
        # "eye" so it doesn't overload one icon meaning both "reveal" and
        # "biometric liveness scan".
        "scan": "M9 2H4a2 2 0 00-2 2v5h2V4h5V2zM20 2h-5v2h5v5h2V4a2 2 0 00-2-2zM4 15H2v5a2 2 0 002 2h5v-2H4v-5zM20 20h-5v2h5a2 2 0 002-2v-5h-2v5zM12 8a4 4 0 100 8 4 4 0 000-8zm0 6a2 2 0 110-4 2 2 0 010 4z",
    }

    if icon_name not in svg_paths:
        icon_name = "settings"

    svg_string = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}"><path d="{svg_paths[icon_name]}" fill="{color}"/></svg>'

    renderer = QSvgRenderer(bytes(svg_string, 'utf-8'))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


def create_app_icon(size=64):
    """Creates a high-resolution professional application logo featuring a
    sleek Privacy Shield + Settings/Vision icon with transparent background.

    The logo uses white/light graphics on a transparent background, making it
    suitable for both Light and Dark themes without needing color adaptation.
    """
    from PyQt5.QtGui import QColor

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Base shield gradient - use current theme's accent teal if available,
    # otherwise default to a dark-theme compatible gradient
    try:
        primary = styles.CURRENT_COLORS["ACCENT_TEAL"]
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor(primary))
        grad.setColorAt(1, QColor(primary).darker(140))
    except Exception:
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor("#33C9BB"))
        grad.setColorAt(1, QColor("#1D8F84"))

    # Shield background
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, size - 8, size - 8, size // 4, size // 4)

    # Inner privacy eye / aperture accent
    inner_pen = QPen(QColor("#FFFFFF"), max(2, size // 16))
    inner_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(inner_pen)
    painter.setBrush(Qt.NoBrush)

    # Eye curve
    center = size // 2
    r = size // 3.5
    painter.drawEllipse(center - int(r), center - int(r), int(r * 2), int(r * 2))

    # Center pupil dot
    painter.setBrush(QBrush(QColor("#FFFFFF")))
    painter.drawEllipse(center - int(r / 2.5), center - int(r / 2.5), int(r * 0.8), int(r * 0.8))

    painter.end()
    return QIcon(pixmap)


def create_scrollable_container(inner_widget):
    """Wraps any page widget in a smooth, hover-activated scroll area."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setWidget(inner_widget)
    return scroll


class StatCard(QFrame):
    def __init__(self, icon_name, title, value, trend="+0%"):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedHeight(130)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setObjectName("CardIcon")
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setPixmap(create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 22).pixmap(22, 22))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl._retheme_icon = lambda: icon_lbl.setPixmap(
            create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 22).pixmap(22, 22))

        trend_lbl = QLabel(trend)
        trend_lbl.setObjectName("TrendValue")
        top_row.addWidget(icon_lbl)
        top_row.addStretch()
        top_row.addWidget(trend_lbl)

        layout.addLayout(top_row)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        value_lbl = QLabel(value)
        value_lbl.setObjectName("StatValue")

        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)

        self._trend_lbl = trend_lbl
        self._value_lbl = value_lbl

    def set_value(self, value):
        """Update the displayed value. For future backend use."""
        self._value_lbl.setText(str(value))

    def set_trend(self, trend):
        """Update the trend/subtitle text. For future backend use."""
        self._trend_lbl.setText(str(trend))


class NotificationBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind_object_names = {
            "success": "NotifySuccess",
            "error": "NotifyError",
            "info": "NotifyInfo",
        }
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self.text_lbl = QLabel("")
        self.text_lbl.setObjectName("NotifyText")
        self.text_lbl.setWordWrap(True)
        layout.addWidget(self.text_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.setObjectName("NotifyInfo")
        self.hide()

    def show_message(self, message, kind="info", timeout_ms=3500):
        self.setObjectName(self._kind_object_names.get(kind, "NotifyInfo"))
        self.style().unpolish(self)
        self.style().polish(self)
        self.text_lbl.setText(message)
        self.show()
        if timeout_ms:
            self._timer.start(timeout_ms)


def load_scaled_pixmap(path, width, height):
    """Load an image file and scale it to fill (width, height)."""
    if not path or not os.path.exists(path):
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def create_blurred_preview_pixmap(width=220, height=52):
    """Generates a realistic Gaussian-blurred preview graphic."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#2A313D"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Simulated blurred face silhouette & text
    # Draw soft overlapping circles
    colors = [QColor(235, 170, 140, 160), QColor(210, 140, 110, 140), QColor(80, 120, 180, 130), QColor(42, 179, 166, 120)]
    for i, c in enumerate(colors):
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(width // 4 + i * 22, height // 2 - 14, 32, 28)

    # Draw blurred text overlay
    painter.setPen(QColor(255, 255, 255, 200))
    font = QFont("Segoe UI", 10, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "GAUSSIAN BLUR")

    painter.end()
    return pixmap


def create_solid_mask_preview_pixmap(width=220, height=52):
    """Generates a pure solid black mask preview graphic with privacy indicator."""
    pixmap = QPixmap(width, height)
    # Always pure black
    pixmap.fill(QColor("#000000"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Draw subtle centered solid mask text
    painter.setPen(QColor(255, 255, 255, 220))
    font = QFont("Segoe UI", 10, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "■ SOLID MASK")

    painter.end()
    return pixmap


# ============================================================================
# NEW PHASE 1 COMPONENTS FOR PRIVAR CY UX IMPROVEMENTS
# ============================================================================

class StatusBar(QFrame):
    """Global application status bar displayed at the bottom of the dashboard.

    Provides visual feedback about the application's current state and can be
    updated by future backend code via set_system_status().

    States:
        - ready: System Ready (default)
        - processing: Processing
        - success: Complete
        - warning: Warning
        - error: Error
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self._state = "ready"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        self._status_dot = QLabel()
        self._status_dot.setFixedSize(12, 12)
        self._status_dot.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_dot)

        self._status_text = QLabel("System Ready")
        self._status_text.setObjectName("StatusBarText")
        self._status_text.setStyleSheet(
            "color: {color}; font-size: 13px; font-weight: 600;"
            .format(color=styles.MUTED_TEXT_COLOR)
        )
        layout.addWidget(self._status_text, 1)

        self._version_lbl = QLabel("PrivARcy v2.4.0")
        self._version_lbl.setStyleSheet(
            "color: {color}; font-size: 11px;".format(color=styles.MUTED_TEXT_COLOR)
        )
        layout.addWidget(self._version_lbl)

        self._update_display()

    def _update_display(self):
        """Update the icon and text based on current state."""
        state_map = {
            "ready": (styles.ACCENT_TEAL, "System Ready"),
            "processing": (styles.ACCENT_TEAL, "Processing"),
            "success": (styles.ACCENT_TEAL, "Complete"),
            "warning": (styles.ACCENT_ORANGE, "Warning"),
            "error": (styles.ACCENT_RED, "Error"),
        }

        color, default_text = state_map.get(self._state, state_map["ready"])

        self._status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 6px; color: {color};"
        )
        self._status_dot.setText("•")
        font = QFont("Arial", 14, QFont.Bold)
        self._status_dot.setFont(font)

        self._status_text.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 600;"
        )
        self._status_text.setText(default_text)

    def set_system_status(self, text, state="ready"):
        """Update the system status.

        Args:
            text: Status text to display
            state: One of 'ready', 'processing', 'success', 'warning', 'error'
        """
        self._state = state
        self._status_text.setText(text)
        self._update_display()

    def retheme(self):
        """Refresh styles when theme changes."""
        self._version_lbl.setStyleSheet(
            "color: {color}; font-size: 11px;".format(color=styles.MUTED_TEXT_COLOR)
        )
        self._update_display()


class EmptyState(QFrame):
    """Reusable empty state component with icon, title, description, and optional action.

    Designed to be displayed when a section has no content yet or all items were removed.
    """

    def __init__(self, title="", description="", icon_name=None,
                 action_text=None, action_callback=None, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(20)

        # Icon
        if icon_name:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                create_icon(icon_name, styles.MUTED_TEXT_COLOR, 64).pixmap(64, 64)
            )
            icon_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(icon_lbl)

        # Title
        if title:
            title_lbl = QLabel(title)
            title_lbl.setObjectName("EmptyStateTitle")
            title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: {color};".format(
                color=styles.TEXT_COLOR
            ))
            title_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_lbl)

        # Description
        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setObjectName("EmptyStateDesc")
            desc_lbl.setStyleSheet("font-size: 13px; color: {color};".format(
                color=styles.MUTED_TEXT_COLOR
            ))
            desc_lbl.setWordWrap(True)
            desc_lbl.setAlignment(Qt.AlignCenter)
            desc_lbl.setMaximumWidth(500)
            layout.addWidget(desc_lbl)

        # Optional action button
        if action_text and action_callback:
            action_btn = QPushButton(action_text)
            action_btn.setObjectName("PrimaryButton")
            action_btn.setMinimumWidth(180)
            action_btn.setFixedHeight(40)
            action_btn.clicked.connect(action_callback)
            layout.addWidget(action_btn)
            layout.setAlignment(action_btn, Qt.AlignCenter)

        layout.addStretch()

    def retheme(self):
        """Refresh styles when theme changes."""
        retheme_widget_tree(self)


class LoadingState(QFrame):
    """Reusable loading state component with simple animation.

    Displays a loading indicator with customizable message.
    """

    def __init__(self, message="Loading...", parent=None):
        super().__init__(parent)
        self.setObjectName("LoadingState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Loading indicator
        self._indicator = QLabel("•")
        self._indicator.setStyleSheet(
            "font-size: 36px; color: {color}; font-weight: bold;"
            .format(color=styles.ACCENT_TEAL)
        )
        self._indicator.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._indicator)

        # Message
        self._msg_lbl = QLabel(message)
        self._msg_lbl.setObjectName("LoadingMessage")
        self._msg_lbl.setStyleSheet(
            "font-size: 14px; color: {color};".format(color=styles.MUTED_TEXT_COLOR)
        )
        self._msg_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._msg_lbl)

        layout.addStretch()

        # Spinner animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._frame = 0

    def set_message(self, message):
        """Update the loading message."""
        self._msg_lbl.setText(message)

    def _tick(self):
        """Animate the loading indicator."""
        self._frame = (self._frame + 1) % 4
        # Use Unicode braille patterns to create a simple spinning effect
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._indicator.setText(frames[self._frame % len(frames)])

    def start(self):
        """Start the loading animation."""
        self._timer.start(80)

    def stop(self):
        """Stop the loading animation."""
        self._timer.stop()
        self._indicator.setText("✓")
        self._indicator.setStyleSheet(
            "font-size: 36px; color: {color}; font-weight: bold;"
            .format(color=styles.ACCENT_TEAL)
        )

    def retheme(self):
        """Refresh styles when theme changes."""
        self._indicator.setStyleSheet(
            "font-size: 36px; color: {color}; font-weight: bold;"
            .format(color=styles.ACCENT_TEAL)
        )
        self._msg_lbl.setStyleSheet(
            "font-size: 14px; color: {color};".format(color=styles.MUTED_TEXT_COLOR)
        )


class ErrorState(QFrame):
    """Reusable error state component with icon, message, and optional retry.

    Displays clear error information with optional retry action.
    """

    def __init__(self, title="Something went wrong",
                 description="Unable to load the requested data.",
                 retry_text=None, on_retry=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ErrorState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(20)

        # Error icon
        error_lbl = QLabel()
        error_lbl.setPixmap(
            create_icon("close", styles.ACCENT_RED, 64).pixmap(64, 64)
        )
        error_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(error_lbl)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setObjectName("ErrorStateTitle")
        title_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: {color};".format(color=styles.ACCENT_RED)
        )
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("ErrorStateDesc")
        desc_lbl.setStyleSheet(
            "font-size: 13px; color: {color};".format(color=styles.MUTED_TEXT_COLOR)
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setMaximumWidth(500)
        layout.addWidget(desc_lbl)

        # Retry button (optional)
        if on_retry and retry_text:
            retry_btn = QPushButton(retry_text)
            retry_btn.setObjectName("SecondaryButton")
            retry_btn.setMinimumWidth(120)
            retry_btn.setFixedHeight(36)
            retry_btn.clicked.connect(on_retry)
            layout.addWidget(retry_btn)
            layout.setAlignment(retry_btn, Qt.AlignCenter)

        layout.addStretch()

    def set_description(self, description):
        """Update the error description."""
        for child in self.findChildren(QLabel):
            if child.objectName() == "ErrorStateDesc":
                child.setText(description)
                break

    def retheme(self):
        """Refresh styles when theme changes."""
        retheme_widget_tree(self)