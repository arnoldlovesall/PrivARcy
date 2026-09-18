# styles.py

LIGHT_COLORS = {
    "BG_COLOR": "#F4F7F6",
    "PANEL_COLOR": "#FFFFFF",
    "BORDER_COLOR": "#E2E8E4",
    "TEXT_COLOR": "#1D2025",
    "MUTED_TEXT_COLOR": "#66707A",
    "ACCENT_TEAL": "#2AB3A6",
    "ACCENT_ORANGE": "#E5A94E",
    "ACCENT_RED": "#E5604E",
    "SHADOW_COLOR": "rgba(0, 0, 0, 0.06)",

    # --- Nav ---
    "NAV_BG_COLOR": "#FFFFFF",
    "NAV_TEXT_COLOR": "#1D2025",
    "NAV_MUTED_TEXT_COLOR": "#66707A",
    "NAV_BORDER_COLOR": "#E2E8E4",
    "NAV_HOVER_COLOR": "#EAF0EF",
    "NAV_HOVER_TEXT_COLOR": "#1D2025",
    "NAV_HOVER_BORDER": "#D5DEDA",
    "NAV_HOVER_SHADOW": "rgba(0, 0, 0, 0.08)",
    "NAV_ACTIVE_COLOR": "#E1EAE8",
    "NAV_ACTIVE_TEXT_COLOR": "#1D2025",
    "NAV_ACTIVE_ACCENT": "#2AB3A6",
}

DARK_COLORS = {
    "BG_COLOR": "#12151A",
    "PANEL_COLOR": "#1B1F26",
    "BORDER_COLOR": "#2A2F38",
    "TEXT_COLOR": "#E8EAED",
    "MUTED_TEXT_COLOR": "#9AA3AF",
    "ACCENT_TEAL": "#33C9BB",
    "ACCENT_ORANGE": "#F0B563",
    "ACCENT_RED": "#F2786A",
    "SHADOW_COLOR": "rgba(0, 0, 0, 0.4)",

    # --- Nav ---
    "NAV_BG_COLOR": "#171B21",           # slightly darker than panel for depth
    "NAV_TEXT_COLOR": "#E8EAED",
    "NAV_MUTED_TEXT_COLOR": "#9AA3AF",
    "NAV_BORDER_COLOR": "#2A2F38",
    "NAV_HOVER_COLOR": "#2A3038",        # visible lift from nav bg
    "NAV_HOVER_TEXT_COLOR": "#FFFFFF",   # brighten text on hover
    "NAV_HOVER_BORDER": "#3A424D",
    "NAV_HOVER_SHADOW": "rgba(0, 0, 0, 0.5)",
    "NAV_ACTIVE_COLOR": "#323A44",
    "NAV_ACTIVE_TEXT_COLOR": "#FFFFFF",
    "NAV_ACTIVE_ACCENT": "#33C9BB",      # teal underline/bar
}

THEMES = {"light": LIGHT_COLORS, "dark": DARK_COLORS}

CURRENT_THEME = "light"
CURRENT_COLORS = LIGHT_COLORS

BG_COLOR = LIGHT_COLORS["BG_COLOR"]
PANEL_COLOR = LIGHT_COLORS["PANEL_COLOR"]
BORDER_COLOR = LIGHT_COLORS["BORDER_COLOR"]
TEXT_COLOR = LIGHT_COLORS["TEXT_COLOR"]
MUTED_TEXT_COLOR = LIGHT_COLORS["MUTED_TEXT_COLOR"]
ACCENT_TEAL = LIGHT_COLORS["ACCENT_TEAL"]
ACCENT_ORANGE = LIGHT_COLORS["ACCENT_ORANGE"]
ACCENT_RED = LIGHT_COLORS["ACCENT_RED"]
SHADOW_COLOR = LIGHT_COLORS["SHADOW_COLOR"]
NAV_HOVER_COLOR = LIGHT_COLORS["NAV_HOVER_COLOR"]


def responsive_margin(base, width, reference=1440, min_val=None, max_val=None):
    """Scale a margin/spacing value against the window's current width.

    `base` is the value designed for a `reference`-px-wide window (1440,
    a common laptop resolution). Below that, margins shrink so content
    isn't cramped-looking on a small window; above it — e.g. the app now
    opens maximized on a 1920/4K display — they grow modestly instead of
    leaving a fixed 30px margin that looks proportionally tiny. Clamped
    to `min_val`/`max_val` (defaulting to 60%/160% of `base`) so extreme
    window sizes never produce a margin so small it clips content or so
    large it wastes most of the window on empty space.
    """
    min_val = min_val if min_val is not None else base * 0.6
    max_val = max_val if max_val is not None else base * 1.6
    scaled = base * (width / reference)
    return int(max(min_val, min(max_val, scaled)))


def themed(widget, style_fn):
    """Apply an inline stylesheet built from the *current* palette and remember
    how to regenerate it on theme switch."""
    widget._theme_style_fn = style_fn
    widget.setStyleSheet(style_fn())
    return widget


def set_theme(name):
    """Switch the live palette ('light' or 'dark') and update every
    module-level color constant in place."""
    global CURRENT_THEME, CURRENT_COLORS
    global BG_COLOR, PANEL_COLOR, BORDER_COLOR, TEXT_COLOR, MUTED_TEXT_COLOR
    global ACCENT_TEAL, ACCENT_ORANGE, ACCENT_RED, SHADOW_COLOR, NAV_HOVER_COLOR
    global GLOBAL_QSS

    palette = THEMES[name]
    CURRENT_THEME = name
    CURRENT_COLORS = palette

    BG_COLOR = palette["BG_COLOR"]
    PANEL_COLOR = palette["PANEL_COLOR"]
    BORDER_COLOR = palette["BORDER_COLOR"]
    TEXT_COLOR = palette["TEXT_COLOR"]
    MUTED_TEXT_COLOR = palette["MUTED_TEXT_COLOR"]
    ACCENT_TEAL = palette["ACCENT_TEAL"]
    ACCENT_ORANGE = palette["ACCENT_ORANGE"]
    ACCENT_RED = palette["ACCENT_RED"]
    SHADOW_COLOR = palette["SHADOW_COLOR"]
    NAV_HOVER_COLOR = palette["NAV_HOVER_COLOR"]

    GLOBAL_QSS = build_qss()
    return GLOBAL_QSS


def build_qss():
    """Build the global stylesheet from the *current* live palette."""
    # SVG data URLs require '#' to be URL-encoded as '%23', otherwise Qt's
    # URL parser treats everything after it as a fragment identifier and
    # silently fails to load the image (renders as a broken-image square
    # or nothing at all). Pre-encode every color the combo arrow needs —
    # normal, muted (disabled), and accent (hover) — so the SVG chevron
    # tracks the theme automatically.
    text_svg = TEXT_COLOR.replace("#", "%23")
    muted_svg = MUTED_TEXT_COLOR.replace("#", "%23")
    accent_svg = ACCENT_TEAL.replace("#", "%23")

    return f"""
* {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    color: {TEXT_COLOR};
}}

QMainWindow {{
    background-color: {BG_COLOR};
}}

/* Sidebar */
QFrame#Sidebar {{
    background-color: {PANEL_COLOR};
    border-right: 1px solid {BORDER_COLOR};
}}

QPushButton#NavButton {{
    background-color: transparent;
    border: none;
    color: {MUTED_TEXT_COLOR};
    text-align: left;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: 500;
    border-radius: 8px;
    margin: 2px 10px;
}}

QPushButton#NavButton:hover {{
    background-color: {NAV_HOVER_COLOR};
    color: {TEXT_COLOR};
}}

QPushButton#NavButton:checked {{
    background-color: rgba(42, 179, 166, 0.14);
    color: {ACCENT_TEAL};
    font-weight: 600;
    border-left: 3px solid {ACCENT_TEAL};
}}

/* Main Content */
QFrame#MainContent {{
    background-color: {BG_COLOR};
}}

QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT_COLOR};
    letter-spacing: 0.5px;
}}

QLabel#PageDesc {{
    font-size: 13px;
    color: {MUTED_TEXT_COLOR};
    line-height: 1.4;
}}

QLabel#SectionHeading {{
    font-size: 17px;
    font-weight: 700;
    color: {TEXT_COLOR};
}}

QLabel#SectionHelper {{
    font-size: 13px;
    color: {MUTED_TEXT_COLOR};
    line-height: 1.4;
}}

/* Cards */
QFrame#Card {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 14px;
}}

QFrame#SelectableCard {{
    background-color: {PANEL_COLOR};
    border: 2px solid {BORDER_COLOR};
    border-radius: 12px;
}}

QFrame#SelectableCard:hover {{
    border: 2px solid {ACCENT_TEAL};
}}

QFrame#SelectableCard[selected="true"] {{
    border: 2px solid {ACCENT_TEAL};
    background-color: rgba(42, 179, 166, 0.07);
}}

QLabel#CardTitle {{
    font-size: 14px;
    color: {MUTED_TEXT_COLOR};
    font-weight: 600;
}}

QLabel#StatValue {{
    font-size: 30px;
    font-weight: bold;
    color: {TEXT_COLOR};
}}

QLabel#TrendValue {{
    font-size: 12px;
    font-weight: bold;
    color: {ACCENT_TEAL};
}}

/* Buttons */
QPushButton#PrimaryButton {{
    background-color: {ACCENT_TEAL};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 10px 22px;
    font-weight: 600;
    font-size: 14px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: #249E93;
}}

QPushButton#PrimaryButton:pressed {{
    background-color: #1E857C;
}}

QPushButton#PrimaryButton:disabled {{
    background-color: {BORDER_COLOR};
    color: {MUTED_TEXT_COLOR};
}}

QPushButton#SecondaryButton {{
    background-color: {PANEL_COLOR};
    color: {TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 500;
    font-size: 13px;
}}

QPushButton#SecondaryButton:hover {{
    border: 1px solid {ACCENT_TEAL};
    color: {ACCENT_TEAL};
    background-color: {NAV_HOVER_COLOR};
}}

QPushButton#SecondaryButton:pressed {{
    background-color: rgba(42, 179, 166, 0.1);
}}

QPushButton#DangerButton {{
    background-color: {PANEL_COLOR};
    color: {ACCENT_RED};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 500;
    font-size: 13px;
}}

QPushButton#DangerButton:hover {{
    border: 1px solid {ACCENT_RED};
    background-color: rgba(229, 96, 78, 0.1);
}}

QPushButton#QuitButton {{
    background-color: transparent;
    color: {MUTED_TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    text-align: left;
    padding: 10px 16px;
    font-weight: 600;
    font-size: 13px;
    margin: 6px 12px 14px 12px;
}}

QPushButton#QuitButton:hover {{
    border: 1px solid {ACCENT_RED};
    color: {ACCENT_RED};
    background-color: rgba(229, 96, 78, 0.12);
}}

QPushButton#QuitButton:pressed {{
    background-color: rgba(229, 96, 78, 0.22);
}}

QFrame#WelcomeHero {{
    background-color: {PANEL_COLOR};
    border: 2px solid {BORDER_COLOR};
    border-radius: 24px;
}}

QLabel#WelcomeTitle {{
    font-size: 34px;
    font-weight: 800;
    color: {TEXT_COLOR};
    letter-spacing: 0.5px;
}}

QLabel#WelcomeTagline {{
    font-size: 14px;
    font-weight: 600;
    color: {ACCENT_TEAL};
    letter-spacing: 0.3px;
    line-height: 1.4;
}}

QLabel#WelcomeDesc {{
    font-size: 13px;
    color: {MUTED_TEXT_COLOR};
    line-height: 1.5;
}}

QFrame#FeaturePillCard {{
    background-color: {BG_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 12px;
}}

/* QMessageBox (Quit confirmation, warnings, errors throughout the app).
   Without explicit rules here, only the universal `* {{ color: ... }}`
   above reaches it — its background stays the OS-native light gray/white
   regardless of theme, so Dark Mode's light text color renders on a
   light background and becomes nearly illegible. */
QMessageBox {{
    background-color: {PANEL_COLOR};
}}

QMessageBox QLabel {{
    color: {TEXT_COLOR};
    font-size: 13px;
    background-color: transparent;
}}

QMessageBox QPushButton {{
    background-color: {BG_COLOR};
    color: {TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 20px;
    min-width: 72px;
    font-weight: 600;
}}

QMessageBox QPushButton:hover {{
    background-color: {NAV_HOVER_COLOR};
    border-color: {ACCENT_TEAL};
}}

QFrame#LiveStatCard {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 12px;
}}

QLabel#LiveStatValue {{
    font-size: 26px;
    font-weight: 800;
    color: {ACCENT_TEAL};
}}

QLabel#LiveStatLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {MUTED_TEXT_COLOR};
    letter-spacing: 0.5px;
}}

QFrame#AuditLogCard {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 12px;
}}

QFrame#AuditLogEntry {{
    background-color: {BG_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
}}

QLabel#DateTimeBadge {{
    font-size: 12px;
    font-weight: 600;
    color: {ACCENT_TEAL};
    background-color: rgba(42, 179, 166, 0.10);
    border: 1px solid rgba(42, 179, 166, 0.30);
    border-radius: 6px;
    padding: 4px 10px;
}}

QPushButton#ThemeToggle {{
    background-color: {PANEL_COLOR};
    color: {TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 16px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton#ThemeToggle:hover {{
    border: 1px solid {ACCENT_TEAL};
    color: {ACCENT_TEAL};
}}

/* ── Inputs: QLineEdit + QComboBox ───────────────────────────────── */
QLineEdit {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 8px 12px;
    color: {TEXT_COLOR};
    font-size: 13px;
}}

QLineEdit:focus {{
    border: 1px solid {ACCENT_TEAL};
}}

QComboBox {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 6px 10px;
    color: {TEXT_COLOR};
    font-size: 13px;
    min-height: 22px;
}}

QComboBox:hover {{
    border: 1px solid {ACCENT_TEAL};
}}

QComboBox:focus {{
    border: 1px solid {ACCENT_TEAL};
}}

QComboBox:disabled {{
    background-color: {BG_COLOR};
    color: {MUTED_TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
}}

/* ── QComboBox: drop-down region + arrow ─────────────────────────── */

/* The clickable arrow region on the right. A subtle vertical divider
   separates it from the text area; hovering the *whole combo* tints
   the region to signal "this opens a dropdown". */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {BORDER_COLOR};
    background: transparent;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}}

QComboBox:hover::drop-down {{
    background-color: {NAV_HOVER_COLOR};
}}

QComboBox:on::drop-down {{
    /* While the popup is open — a slightly stronger tint so the user
       can see which combo is currently expanded at a glance. */
    background-color: {NAV_HOVER_COLOR};
    border-left: 1px solid {ACCENT_TEAL};
}}

/* Arrow glyph as an inline SVG data URL. Drawn as a soft rounded
   chevron (not a sharp triangle) — it reads better at small sizes and
   matches the icon weight used elsewhere in the app (see create_icon
   in components.py, which uses 1.75–2px strokes for the nav icons).

   Color is baked into the SVG per theme, URL-encoded as %23 for '#'
   (otherwise Qt's URL parser eats the hex as a fragment marker). */
QComboBox::down-arrow {{
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8' fill='none'><path d='M1.5 2 L6 6.5 L10.5 2' stroke='{text_svg}' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'/></svg>");
    width: 12px;
    height: 8px;
    margin-right: 8px;
}}

QComboBox:hover::down-arrow {{
    /* On hover, the chevron picks up the accent color to match the
       combo's border-color change above it. */
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8' fill='none'><path d='M1.5 2 L6 6.5 L10.5 2' stroke='{accent_svg}' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}}

QComboBox::down-arrow:disabled {{
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8' fill='none'><path d='M1.5 2 L6 6.5 L10.5 2' stroke='{muted_svg}' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}}

/* The popup list is a top-level widget, NOT a child of the QComboBox —
   it must be styled via `QComboBox QAbstractItemView`, otherwise it
   renders as an OS-native white box regardless of the surrounding
   theme (this is the classic "dark mode combo still looks light" bug). */
QComboBox QAbstractItemView {{
    background-color: {PANEL_COLOR};
    color: {TEXT_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 4px;
    outline: 0;                       /* kill the dotted focus rect */
    selection-background-color: {ACCENT_TEAL};
    selection-color: #FFFFFF;
}}

QComboBox QAbstractItemView::item {{
    min-height: 24px;
    padding: 4px 8px;
    border-radius: 4px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {NAV_HOVER_COLOR};
    color: {TEXT_COLOR};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {ACCENT_TEAL};
    color: #FFFFFF;
}}

QSlider::groove:horizontal {{
    border: none;
    height: 6px;
    background: {BORDER_COLOR};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {ACCENT_TEAL};
    border: 2px solid {PANEL_COLOR};
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}}

QSlider::handle:horizontal:hover {{
    background: #249E93;
    width: 20px;
    height: 20px;
    margin: -7px 0;
    border-radius: 10px;
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT_TEAL};
    border-radius: 3px;
}}

QLabel#PillTeal {{
    background-color: rgba(42, 179, 166, 0.12);
    color: {ACCENT_TEAL};
    border: 1px solid rgba(42, 179, 166, 0.3);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#PillOrange {{
    background-color: rgba(229, 169, 78, 0.15);
    color: {ACCENT_ORANGE};
    border: 1px solid rgba(229, 169, 78, 0.3);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#PillRed {{
    background-color: rgba(229, 96, 78, 0.12);
    color: {ACCENT_RED};
    border: 1px solid rgba(229, 96, 78, 0.3);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#CodeTag {{
    background-color: rgba(42, 179, 166, 0.12);
    color: {ACCENT_TEAL};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    font-weight: bold;
    padding: 3px 8px;
    border-radius: 6px;
}}

QLabel#BrandName {{
    font-size: 18px;
    font-weight: 800;
    color: {TEXT_COLOR};
    letter-spacing: 0.5px;
}}

QLabel#BrandTag {{
    font-size: 10px;
    font-weight: 700;
    color: {ACCENT_TEAL};
    letter-spacing: 1.8px;
}}

QLabel#SectionLabel {{
    font-size: 11px;
    font-weight: bold;
    color: {MUTED_TEXT_COLOR};
    letter-spacing: 1.5px;
    padding: 0px 20px;
}}

QFrame#SidebarDivider {{
    background-color: {BORDER_COLOR};
    max-height: 1px;
    min-height: 1px;
}}

QCheckBox {{
    font-size: 13px;
    font-weight: 500;
    spacing: 10px;
    padding: 6px 4px;
    color: {TEXT_COLOR};
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 6px;
    border: 2px solid {BORDER_COLOR};
    background-color: {PANEL_COLOR};
}}

QCheckBox::indicator:hover {{
    border: 2px solid {ACCENT_TEAL};
    background-color: {NAV_HOVER_COLOR};
}}

QCheckBox::indicator:checked {{
    border: 2px solid {ACCENT_TEAL};
    background-color: {ACCENT_TEAL};
}}

QRadioButton {{
    font-size: 13px;
    font-weight: 500;
    spacing: 10px;
    padding: 6px 4px;
    color: {TEXT_COLOR};
}}

QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 10px;
    border: 2px solid {BORDER_COLOR};
    background-color: {PANEL_COLOR};
}}

QRadioButton::indicator:hover {{
    border: 2px solid {ACCENT_TEAL};
    background-color: {NAV_HOVER_COLOR};
}}

QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT_TEAL};
    background-color: {ACCENT_TEAL};
}}

QRadioButton:checked {{
    color: {ACCENT_TEAL};
    font-weight: 700;
}}

QFrame#OptionCard {{
    background-color: {PANEL_COLOR};
    border: 2px solid {BORDER_COLOR};
    border-radius: 12px;
}}

QFrame#OptionCard:hover {{
    border: 2px solid {ACCENT_TEAL};
}}

QFrame#OptionCard[selected="true"] {{
    border: 2px solid {ACCENT_TEAL};
    background-color: rgba(42, 179, 166, 0.06);
}}

QLabel#OptionSwatchMask {{
    background-color: #000000;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
}}

QLabel#OptionSwatchBlur {{
    background-color: {BORDER_COLOR};
    border-radius: 8px;
}}

QFrame#SettingsGroup {{
    background-color: {PANEL_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 14px;
}}

QLabel#GroupTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {TEXT_COLOR};
}}

QLabel#GroupHint {{
    font-size: 12px;
    color: {MUTED_TEXT_COLOR};
    line-height: 1.4;
}}

QFrame#NotifySuccess {{
    background-color: rgba(42, 179, 166, 0.12);
    border: 1px solid {ACCENT_TEAL};
    border-radius: 8px;
}}
QFrame#NotifyError {{
    background-color: rgba(229, 96, 78, 0.12);
    border: 1px solid {ACCENT_RED};
    border-radius: 8px;
}}
QFrame#NotifyInfo {{
    background-color: rgba(42, 179, 166, 0.08);
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
}}
QLabel#NotifyText {{
    font-size: 13px;
    font-weight: 600;
}}

QProgressBar {{
    background-color: {BORDER_COLOR};
    border: none;
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT_TEAL};
    border-radius: 6px;
}}

QLabel#PhotoPreview {{
    background-color: {BORDER_COLOR};
    border-radius: 10px;
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: transparent;
    min-height: 25px;
    border-radius: 4px;
}}
QScrollArea:hover QScrollBar::handle:vertical,
QScrollBar::vertical:hover QScrollBar::handle:vertical {{
    background: {BORDER_COLOR};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


GLOBAL_QSS = build_qss()