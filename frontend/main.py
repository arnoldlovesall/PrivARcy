# main.py
import sys, os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QStackedWidget, QFrame,
                             QGraphicsOpacityEffect, QShortcut, QMessageBox)
from PyQt5.QtGui import QIcon, QPixmap, QKeySequence
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSettings, QTimer

import styles
from components import (create_icon, create_app_icon, retheme_widget_tree,
                        create_scrollable_container, StatusBar)
from Home import HomePage
from Process import ProcessPage
from Live import LivePage
from FaceRegister import FaceRegisterPage
from Review import ReviewPage
from Results import ResultsPage
from Settings import SettingsPage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
# Wordmark logo — two variants, one per theme, since a light-teal-gradient
# mark that reads clearly on a dark background all but disappears on a
# light one, and vice versa. Used on the Welcome screen and the sidebar
# header, where there's room for the "PrivARcy" text to be legible.
LOGO_PATH_DARK = os.path.join(ASSETS_DIR, "privarcy-main-logo.png")
LOGO_PATH_LIGHT = os.path.join(ASSETS_DIR, "privarcy-main-logo.png")
# Icon-only mark (no wordmark text) for the window/taskbar icon, which
# renders far too small for text to be legible anyway. Not theme-aware:
# OS chrome doesn't follow the in-app theme.
ICON_PATH = os.path.join(ASSETS_DIR, "privarcy-main-logo.png")


def current_logo_path():
    return LOGO_PATH_DARK if styles.CURRENT_THEME == "dark" else LOGO_PATH_LIGHT

BACKEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
from src.integration import BackendService

# Detection labels -> the 5 summary buckets Results.py's cards show. This is
# a coarser breakdown than Review.py's 5 category boxes (FACE/ID/DOCUMENT/
# CREDENTIAL/LICENSE_PLATE) — Results gives an at-a-glance summary, Review
# gives per-item detail, so they're allowed to group things differently.
# Matched against the raw detection label text (not the review category)
# so "Screens" — which the pipeline folds into DOCUMENT for review purposes
# — can still get its own bucket here.
def _results_bucket(label: str) -> str:
    text = label.lower()
    if "face" in text:
        return "Faces"
    if "credential" in text or "credit" in text or "debit" in text or "card" in text:
        return "Credentials"
    if "screen" in text:
        return "Screens"
    if "document" in text:
        return "Documents"
    return "Other"


class WelcomePage(QWidget):
    """Initial Welcome & Landing page displayed when main.py is launched."""
    def __init__(self, on_get_started, on_toggle_theme):
        super().__init__()
        self.on_get_started = on_get_started
        self.on_toggle_theme = on_toggle_theme

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(40, 30, 40, 40)
        main_layout.setSpacing(24)

        # Top Bar: Version & Theme toggle
        top_bar = QHBoxLayout()
        ver_badge = QLabel("PrivARcy v2.4.0 · Local Privacy Engine")
        ver_badge.setObjectName("PillTeal")
        top_bar.addWidget(ver_badge)
        top_bar.addStretch()

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self._update_theme_btn_text()
        self.theme_btn.clicked.connect(self.on_toggle_theme)
        top_bar.addWidget(self.theme_btn)
        main_layout.addLayout(top_bar)

        # Hero Card
        hero_card = QFrame()
        hero_card.setObjectName("WelcomeHero")
        # Capped width so the card stays well-proportioned instead of
        # stretching edge-to-edge once the window auto-maximizes on
        # Get Started (see MainWindow.start_app).
        hero_card.setMaximumWidth(920)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(40, 36, 40, 36)
        hero_layout.setSpacing(16)
        hero_layout.setAlignment(Qt.AlignCenter)
        # Kept as instance attributes so apply_responsive_margins() (called
        # from MainWindow.resizeEvent) can rescale these against the
        # window's current width instead of leaving them fixed.
        self._welcome_content_layout = main_layout
        self._hero_layout = hero_layout

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.logo_label.setStyleSheet("background: transparent;")
        self._update_logo_pixmap()
        hero_layout.addWidget(self.logo_label, alignment=Qt.AlignHCenter)

        title_lbl = QLabel("PrivARcy")
        title_lbl.setObjectName("WelcomeTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(title_lbl)

        tagline_lbl = QLabel(
            "A Video Privacy Protection System Using Custom-Trained YOLO26 and "
            "TrOCR with Rule-Based Sensitivity Classification and Confidence-Gated Human Review"
        )
        tagline_lbl.setObjectName("WelcomeTagline")
        tagline_lbl.setAlignment(Qt.AlignCenter)
        tagline_lbl.setWordWrap(True)
        tagline_lbl.setMaximumWidth(780)
        hero_layout.addWidget(tagline_lbl)

        desc_lbl = QLabel(
            "Automated bystander protection, sensitive credential masking, and consented identity management. "
            "Runs completely locally with full privacy guarantee."
        )
        desc_lbl.setObjectName("WelcomeDesc")
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setMaximumWidth(720)
        hero_layout.addWidget(desc_lbl)

        features_layout = QHBoxLayout()
        features_layout.setSpacing(16)

        feat1 = self._create_feature_card(
            "shield", "Intelligent Redaction",
            "Deep neural detection for bystander faces, credentials, IDs, and digital screens."
        )
        feat2 = self._create_feature_card(
            "face", "Consented Registry",
            "Register authorized participant faces to preserve them while redacting everyone else."
        )
        feat3 = self._create_feature_card(
            "speed", "Dual Pipelines",
            "High-accuracy GPU offline processing and lightweight real-time stream monitoring."
        )

        features_layout.addWidget(feat1)
        features_layout.addWidget(feat2)
        features_layout.addWidget(feat3)
        hero_layout.addSpacing(10)
        hero_layout.addLayout(features_layout)

        hero_layout.addSpacing(12)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.setSpacing(16)

        get_started_btn = QPushButton("  Get Started  →")
        get_started_btn.setObjectName("PrimaryButton")
        get_started_btn.setMinimumWidth(220)
        get_started_btn.setFixedHeight(50)
        get_started_btn.setCursor(Qt.PointingHandCursor)
        get_started_btn.setStyleSheet("font-size: 16px; font-weight: bold;")
        get_started_btn.clicked.connect(self.on_get_started)

        btn_row.addWidget(get_started_btn)
        hero_layout.addLayout(btn_row)

        main_layout.addWidget(hero_card, alignment=Qt.AlignHCenter)
        main_layout.addStretch()

        self.scroll = create_scrollable_container(content)
        root_layout.addWidget(self.scroll)

    def _update_logo_pixmap(self):
        # Use the theme-aware vector icon for consistent appearance in both
        # Light and Dark modes. The PNG asset is kept as a fallback only.
        pixmap = QPixmap(current_logo_path())
        if not pixmap.isNull():
            scaled = pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled)
            # Without an explicit fixed size, this QLabel's default
            # sizeHint()/layout negotiation (as a non-text, pixmap-only
            # label being stretched horizontally to the layout's full
            # width) computed a height shorter than the pixmap itself —
            # the top of the logo was being clipped, not just displayed
            # small. Locking the label to the pixmap's own size removes
            # that ambiguity entirely.
            self.logo_label.setFixedSize(scaled.size())
        else:
            fallback = create_app_icon(140).pixmap(140, 140)
            self.logo_label.setPixmap(fallback)
            self.logo_label.setFixedSize(fallback.size())
        # Ensure the label background stays transparent regardless of theme
        self.logo_label.setStyleSheet("background: transparent;")
        self.logo_label.setAttribute(Qt.WA_TranslucentBackground, True)

    def _create_feature_card(self, icon_name, title, desc):
        card = QFrame()
        card.setObjectName("FeaturePillCard")
        card.setMinimumWidth(220)  # matches the width assumed by the wrap-height calc below
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_icon(icon_name, styles.ACCENT_TEAL, 24).pixmap(24, 24))
        icon_lbl._retheme_icon = lambda: icon_lbl.setPixmap(
            create_icon(icon_name, styles.CURRENT_COLORS['ACCENT_TEAL'], 24).pixmap(24, 24))
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        styles.themed(desc_lbl, lambda: f"color: {styles.MUTED_TEXT_COLOR}; font-size: 12px; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        # A QLabel with word-wrap inside this card's layout — itself
        # nested inside hero_layout, which has setAlignment(Qt.AlignCenter)
        # — doesn't reliably get its heightForWidth() renegotiated once
        # laid out at its final (narrower, 3-column) width, so the card
        # was clipping the last line or two of every description instead
        # of growing to fit them (the same root cause as an earlier bug
        # in the Welcome tagline label). Computing the wrapped height
        # explicitly via QFontMetrics — instead of trusting Qt's
        # automatic sizeHint here — sidesteps that negotiation entirely.
        metrics = desc_lbl.fontMetrics()
        wrapped_rect = metrics.boundingRect(
            0, 0, 230, 1000, Qt.TextWordWrap, desc
        )
        desc_lbl.setMinimumHeight(int(wrapped_rect.height() * 1.4) + 4)
        layout.addWidget(desc_lbl)

        return card

    def _update_theme_btn_text(self):
        if styles.CURRENT_THEME == "light":
            self.theme_btn.setText("🌙  Dark Mode")
        else:
            self.theme_btn.setText("☀️  Light Mode")

    def retheme(self):
        self._update_theme_btn_text()
        self._update_logo_pixmap()
        retheme_widget_tree(self)

    def apply_responsive_margins(self, width):
        """Rescale the Welcome page's outer content margins and hero-card
        padding against the window's current width — see
        styles.responsive_margin(). Called from MainWindow.resizeEvent."""
        outer = styles.responsive_margin(40, width)
        top = styles.responsive_margin(30, width)
        self._welcome_content_layout.setContentsMargins(outer, top, outer, outer)
        inner_h = styles.responsive_margin(40, width)
        inner_v = styles.responsive_margin(36, width)
        self._hero_layout.setContentsMargins(inner_h, inner_v, inner_h, inner_v)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrivARcy Dashboard")
        self._set_app_icon()
        self.resize(1400, 900)
        self.current_page = "Home"

        # One BackendService shared by every page, instead of Process.py and
        # FaceRegister.py each creating their own — otherwise Settings
        # changes, registered faces, and the confidence-gated review queue
        # would silently diverge between pages.
        self.backend = BackendService()

        # Persist the user's Light/Dark preference across restarts.
        self.settings = QSettings("PrivARcy", "Dashboard")
        saved_theme = self.settings.value("theme", "light")
        # Always apply the saved theme's stylesheet on startup.
        # Previously this was guarded by `if saved_theme != styles.CURRENT_THEME`,
        # which caused the stylesheet to be missing on first launch when the
        # default theme ("light") matched the saved theme ("light").
        new_qss = styles.set_theme(saved_theme)
        QApplication.instance().setStyleSheet(new_qss)

        # Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # App Stack: Screen 0 = Welcome / Get Started, Screen 1 = Dashboard
        self.dashboard_stack = QStackedWidget()
        self.main_layout.addWidget(self.dashboard_stack)

        # 1. Welcome Screen (shown on launch)
        self.welcome_page = WelcomePage(
            on_get_started=self.start_app,
            on_toggle_theme=self.toggle_theme
        )
        self.dashboard_stack.addWidget(self.welcome_page)

        # 2. Main Dashboard (Sidebar + Pages)
        self.dashboard = self.create_dashboard()
        self.dashboard_stack.addWidget(self.dashboard)
        process_page = self._get_page("Process")
        if process_page is not None:
            process_page.on_processing_complete = self._handle_processing_complete

        # Start on the Welcome screen
        self.dashboard_stack.setCurrentIndex(0)

        # CRITICAL FIX: Schedule a full retheme after the window is constructed
        # This fixes broken inline styles on startup when saved theme differs.
        QTimer.singleShot(0, self._apply_retheme)

        # Set up keyboard shortcuts
        self._setup_keyboard_shortcuts()

    def _set_app_icon(self):
        pixmap = QPixmap(ICON_PATH)
        if not pixmap.isNull():
            self.setWindowIcon(QIcon(pixmap))
        else:
            self.setWindowIcon(create_app_icon(64))

    def start_app(self):
        """Switch from the Welcome screen to the Dashboard without a fade/repaint effect."""
        self.dashboard_stack.setCurrentIndex(1)
        self.navigate("Home", animate=False)
        self._refresh_home_stats()
        # Maximized rather than true showFullScreen(): fills the screen
        # like a fullscreen app, but keeps the title bar (minimize/
        # restore/close) so the window stays easy to get out of.
        self.showMaximized()

    def fade_in(self, widget):
        """Animates the opacity of a widget for smooth transitions"""
        self.effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim.start()

    def create_dashboard(self):
        dashboard = QWidget()
        layout = QHBoxLayout(dashboard)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- SIDEBAR ---
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 10)
        sidebar_layout.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(20, 0, 20, 0)
        brand_row.setSpacing(12)

        self.sidebar_logo_label = QLabel()
        self._update_sidebar_logo()
        brand_row.addWidget(self.sidebar_logo_label)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_name = QLabel("PrivARcy")
        brand_name.setObjectName("BrandName")
        brand_tag = QLabel("PRIVACY REDACTION")
        brand_tag.setObjectName("BrandTag")
        brand_text.addWidget(brand_name)
        brand_text.addWidget(brand_tag)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()

        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(18)

        divider = QFrame()
        divider.setObjectName("SidebarDivider")
        divider.setFixedHeight(1)
        sidebar_layout.addWidget(divider)
        sidebar_layout.addSpacing(14)

        section_lbl = QLabel("MAIN MENU")
        section_lbl.setObjectName("SectionLabel")
        sidebar_layout.addWidget(section_lbl)
        sidebar_layout.addSpacing(6)

        # Nav Items
        self.nav_buttons = []
        self.page_stack = QStackedWidget()
        self.pages = []

        nav_items = [
            ("home", "Home", HomePage),
            ("process", "Process", ProcessPage),
            ("live", "Live", LivePage),
            ("face", "Face Register", FaceRegisterPage),
            ("review", "Review", ReviewPage),
            ("results", "Results", ResultsPage),
            ("settings", "Settings", SettingsPage)
        ]

        for icon_name, name, page_class in nav_items:
            btn = QPushButton(f"   {name}")
            btn.setObjectName("NavButton")
            btn.setIcon(create_icon(icon_name, styles.MUTED_TEXT_COLOR, 20))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("icon_name", icon_name)

            if page_class is ResultsPage:
                page_widget = page_class(self.navigate, self.reset_session)
            elif page_class is ProcessPage:
                page_widget = page_class(self.navigate, self.backend)
            elif page_class is HomePage:
                page_widget = page_class(self.navigate)
            elif page_class is ReviewPage:
                page_widget = page_class(self.backend)
            elif page_class in (FaceRegisterPage, SettingsPage, LivePage):
                page_widget = page_class(self.backend)
            else:
                page_widget = page_class()

            self.page_stack.addWidget(page_widget)
            self.pages.append((name, page_widget))

            btn.clicked.connect(lambda checked, n=name: self.navigate(n))

            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        divider2 = QFrame()
        divider2.setObjectName("SidebarDivider")
        divider2.setFixedHeight(1)
        sidebar_layout.addWidget(divider2)
        sidebar_layout.addSpacing(4)

        quit_btn = QPushButton("  Quit PrivARcy")
        quit_btn.setObjectName("QuitButton")
        quit_btn.setIcon(create_icon("quit", styles.ACCENT_RED, 18))
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setToolTip("Exit and close PrivARcy")
        quit_btn.clicked.connect(self.close)
        sidebar_layout.addWidget(quit_btn)

        # --- MAIN CONTENT AREA ---
        main_content = QFrame()
        main_content.setObjectName("MainContent")
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)
        # Kept as an instance attribute so resizeEvent (below) can rescale
        # these margins against the window's current width instead of
        # leaving them fixed regardless of how large the window gets —
        # relevant now that the app opens maximized by default.
        self._main_content_layout = main_layout

        header = QHBoxLayout()
        header_title_layout = QVBoxLayout()
        self.header_title = QLabel("Dashboard")
        self.header_title.setObjectName("PageTitle")
        desc = QLabel("Overview of your PrivARcy system")
        desc.setObjectName("PageDesc")
        header_title_layout.addWidget(self.header_title)
        header_title_layout.addWidget(desc)

        header.addLayout(header_title_layout)
        header.addStretch()

        status = QLabel("● System Online")
        styles.themed(status, lambda: f"color: {styles.ACCENT_TEAL}; font-weight: bold;")
        header.addWidget(status)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self._update_theme_button_label()
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)

        main_layout.addLayout(header)
        main_layout.addWidget(self.page_stack)

        # --- STATUS BAR ---
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)

        layout.addWidget(sidebar)
        layout.addWidget(main_content, 1)
        return dashboard

    def _update_sidebar_logo(self):
        pixmap = QPixmap(current_logo_path())
        if not pixmap.isNull():
            self.sidebar_logo_label.setPixmap(pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.sidebar_logo_label.setPixmap(create_app_icon(38).pixmap(38, 38))

    def navigate(self, name, animate=False):
        """Switch pages directly to avoid opacity effects that can look like a re-render."""
        self.current_page = name
        self._recolor_nav_icons(active_name=name)

        self.header_title.setText(name)

        page_map = {n: i for i, (n, _) in enumerate(self.pages)}
        self.page_stack.setCurrentIndex(page_map[name])

        if name == "Home":
            self._refresh_home_stats()

        # Page transitions are intentionally not animated.
        # This keeps the UI stable and prevents the temporary opacity effect.
        if animate:
            self.fade_in(self.page_stack.currentWidget())

    def _refresh_home_stats(self):
        """Push real numbers from the backend into the Home dashboard tiles.

        Pending count and average confidence come from the Review page's
        own queue, not BackendService.review_store — file-processing
        results are pushed straight into Review.set_detections() (see
        _handle_processing_complete) and never touch that store, so
        review_store only reflects the live-camera path. Reading from
        Review.queue instead means this always matches what's actually
        on-screen, regardless of which path produced it — the definitive
        place to extend if any future data source needs to show up here.
        """
        home = self._get_page("Home")
        if home is None:
            return
        overview = self.backend.overview()

        review = self._get_page("Review")
        review_items = review.queue if review is not None else []
        pending = sum(1 for i in review_items if i.get("status") == "pending")
        scored = [i["confidence"] for i in review_items if i.get("confidence") is not None]
        avg_confidence = f"{sum(scored) / len(scored) * 100:.1f}%" if scored else "—"

        home.set_overview_stats(
            processed=overview["completed_jobs"],
            faces=overview["registered_faces"],
            pending=pending,
            confidence=avg_confidence,
        )
        home.set_history(self.backend.get_history(5))

    def _recolor_nav_icons(self, active_name=None):
        if active_name is None:
            active_name = self.current_page
        for b in self.nav_buttons:
            is_active = b.text().strip() == active_name
            b.setChecked(is_active)
            icon_name = b.property("icon_name")
            color = styles.ACCENT_TEAL if is_active else styles.MUTED_TEXT_COLOR
            b.setIcon(create_icon(icon_name, color, 20))

    def _update_theme_button_label(self):
        if styles.CURRENT_THEME == "light":
            self.theme_btn.setText("🌙  Dark Mode")
        else:
            self.theme_btn.setText("☀️  Light Mode")

    def toggle_theme(self):
        new_theme = "dark" if styles.CURRENT_THEME == "light" else "light"
        new_qss = styles.set_theme(new_theme)

        QApplication.instance().setStyleSheet(new_qss)
        self.settings.setValue("theme", new_theme)
        self._update_theme_button_label()

        QTimer.singleShot(0, self._apply_retheme)

    def _apply_retheme(self):
        """Deferred heavy retheme pass to keep UI completely responsive."""
        self._recolor_nav_icons()
        self._update_sidebar_logo()
        self._set_app_icon()
        self.welcome_page.retheme()
        retheme_widget_tree(self.dashboard)
        self.status_bar.retheme()
        for name, page in self.pages:
            retheme = getattr(page, "retheme", None)
            if callable(retheme):
                retheme()

    def _setup_keyboard_shortcuts(self):
        """Set up global keyboard shortcuts for common, already-implemented
        frontend actions only (per the Phase 1 spec: no shortcuts for
        functionality that doesn't exist yet)."""
        # Ctrl+, — Settings
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._shortcut_settings)
        # Ctrl+Q — Quit
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        # Ctrl+O — Open Video (Process page's existing file picker)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._shortcut_open_video)
        # Ctrl+S — Save/Export (Results page's existing export action)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._shortcut_export)
        # Space — Play/Pause is registered locally on the Live page itself
        # (see Live.py) rather than as a window-wide shortcut, so it doesn't
        # swallow spacebar presses while typing in text fields on other pages.
        # Ctrl+1..7 — Navigate to pages
        page_shortcuts = ["Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6", "Ctrl+7"]
        for i, sc in enumerate(page_shortcuts):
            if i < len(self.pages):
                name = self.pages[i][0]
                QShortcut(QKeySequence(sc), self, activated=lambda n=name: self.navigate(n))
        # Esc — Cancel the current page's active action if it has one,
        # otherwise fall back to returning Home.
        QShortcut(QKeySequence("Esc"), self, activated=self._shortcut_escape)

    def _shortcut_settings(self):
        """Navigate to the Settings page."""
        self.navigate("Settings")

    def _get_page(self, name):
        for n, page in self.pages:
            if n == name:
                return page
        return None

    def _shortcut_open_video(self):
        """Ctrl+O — jump to Process and open its existing file picker."""
        self.navigate("Process")
        page = self._get_page("Process")
        if page is not None and hasattr(page, "select_video"):
            page.select_video()

    def _shortcut_export(self):
        """Ctrl+S — trigger the Results page's existing export action."""
        page = self._get_page("Results")
        if page is not None and hasattr(page, "export_output"):
            self.navigate("Results")
            page.export_output()

    def _shortcut_escape(self):
        """Esc — cancel an in-progress action on the current page if one
        exists, otherwise return to Home."""
        page = self._get_page(self.current_page)
        if page is not None and hasattr(page, "_on_cancel_clicked"):
            page._on_cancel_clicked()
            return
        self.navigate("Home")

    def resizeEvent(self, event):
        """Rescale key content margins against the window's current width
        — see styles.responsive_margin(). Runs on every resize, including
        the initial maximize on launch, so margins actually reflect
        whatever size the window ends up at rather than a fixed value
        tuned for one particular window size."""
        super().resizeEvent(event)
        width = self.width()
        if hasattr(self, "_main_content_layout"):
            m = styles.responsive_margin(30, width)
            self._main_content_layout.setContentsMargins(m, m, m, m)
        welcome = getattr(self, "welcome_page", None)
        if welcome is not None and hasattr(welcome, "apply_responsive_margins"):
            welcome.apply_responsive_margins(width)

    def closeEvent(self, event):
        """Confirm before exiting — covers both the window's X button and
        the sidebar's Quit PrivARcy button, since both route through
        QMainWindow.close() -> this event."""
        reply = QMessageBox.question(
            self, "Quit PrivARcy",
            "Are you sure you want to exit this app?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            event.ignore()
            return

        # Stop a live camera session cleanly rather than leaving its
        # capture/detection threads orphaned when the process exits.
        if self.backend.live_session and self.backend.live_session.is_live:
            self.backend.stop_live()
        event.accept()

    def reset_session(self):
        """Clear the Process/Review/Results session state (Process Another
        Video's 'Reset' step) and return the user to Home, so the previous
        video's data never carries over into the next session."""
        for name in ("Process", "Review", "Results"):
            page = self._get_page(name)
            if page is not None and hasattr(page, "reset"):
                page.reset()
        self.navigate("Home")

    def _handle_processing_complete(self, result):
        """Deliver a completed local processing result to Review and Results."""
        review = self._get_page("Review")
        results = self._get_page("Results")
        if review is not None:
            review.set_detections(result.detections)
        if results is not None:
            # Bucket by the raw detection label into Results.py's 5 summary
            # cards (Faces/Credentials/Documents/Screens/Other) — using
            # item["label"] directly here (as before) doesn't work because
            # those cards look up an exact key match, and the pipeline's
            # labels ("Ids", "License Plates", ...) don't match any of the
            # 5 card names, so 4 of 5 cards would silently stay at zero.
            categories = {}
            for item in result.detections:
                bucket = _results_bucket(item["label"])
                categories[bucket] = categories.get(bucket, 0) + 1
            confirmed = sum(1 for i in result.detections if i["status"] == "confirmed")
            results.set_results({
                "output_path": result.output_path,
                "frames_processed": str(result.frames),
                "total_redactions": str(result.redactions),
                "categories": categories,
                "summary": {
                    "total_detections": len(result.detections),
                    "auto_redacted": confirmed,
                },
            })
        # Feed real numbers back into the Home dashboard tiles + activity log.
        source_name = (
            result.detections[0]["source"] if result.detections
            else os.path.basename(result.output_path)
        )
        self.backend.record_history(
            source_name=source_name, frames=result.frames,
            total_detections=len(result.detections), redactions=result.redactions,
            output_path=result.output_path,
        )
        self._refresh_home_stats()

    def set_system_status(self, text, state="ready"):
        """Public API for backend code to update the global status bar."""
        if hasattr(self, 'status_bar'):
            self.status_bar.set_system_status(text, state)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Do NOT set stylesheet here; MainWindow handles it correctly.
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())
