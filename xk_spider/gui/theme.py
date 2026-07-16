"""Application theme tokens and the shared Qt stylesheet.

The palette follows AstrBot's restrained blue/neutral visual language while
remaining a native Qt implementation.  Keeping the tokens in one module makes
light/dark switching deterministic and avoids per-widget colour drift.
"""


PALETTES = {
    "light": {
        "BASE": "#F3F6FA",
        "MANTLE": "#EAF0F6",
        "CRUST": "#101828",
        "SURFACE0": "#FFFFFF",
        "SURFACE1": "#F2F4F7",
        "SURFACE2": "#D0D5DD",
        "TEXT": "#1B1C1D",
        "SUBTEXT1": "#29364A",
        "SUBTEXT0": "#5D6B7F",
        "OVERLAY0": "#98A2B3",
        "BLUE": "#359AD3",
        "LAVENDER": "#66B7E4",
        "SAPPHIRE": "#2386C2",
        "GREEN": "#12B76A",
        "RED": "#F04438",
        "YELLOW": "#F79009",
        "PEACH": "#F79009",
        "MAUVE": "#7F56D9",
        "BORDER": "#DEE5ED",
        "SHADOW": "rgba(16, 24, 40, 0.12)",
        "TERMINAL": "#111827",
        "TERMINAL_TEXT": "#D0D5DD",
    },
    "dark": {
        "BASE": "#111419",
        "MANTLE": "#171B21",
        "CRUST": "#0B0D0F",
        "SURFACE0": "#1D2229",
        "SURFACE1": "#272E37",
        "SURFACE2": "#3B4552",
        "TEXT": "#F5F7FA",
        "SUBTEXT1": "#E2E7ED",
        "SUBTEXT0": "#B5C0CD",
        "OVERLAY0": "#667085",
        "BLUE": "#68B8E6",
        "LAVENDER": "#91D2F2",
        "SAPPHIRE": "#4CA6D8",
        "GREEN": "#32D583",
        "RED": "#FF6B6B",
        "YELLOW": "#FDB022",
        "PEACH": "#FEC84B",
        "MAUVE": "#B692F6",
        "BORDER": "#35404C",
        "SHADOW": "rgba(0, 0, 0, 0.38)",
        "TERMINAL": "#0B0D0F",
        "TERMINAL_TEXT": "#D0D5DD",
    },
}


class Colors:
    """Mutable compatibility palette used by the existing dialogs."""


def apply_palette(mode="light"):
    mode = mode if mode in PALETTES else "light"
    for name, value in PALETTES[mode].items():
        setattr(Colors, name, value)
    Colors.MODE = mode
    return mode


apply_palette("light")


def build_stylesheet(mode="light"):
    apply_palette(mode)
    c = Colors
    return f"""
    QMainWindow, QDialog, QWidget {{
        background-color: {c.BASE};
        color: {c.TEXT};
    }}
    QWidget#loginPage, QWidget#workspacePage, QWidget#appRoot {{
        background-color: {c.BASE};
    }}
    QFrame#loginCard, QFrame#topBar, QFrame#panelCard, QFrame#sectionCard {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.BORDER};
        border-radius: 22px;
    }}
    QFrame#loginCard, QFrame#topBar, QFrame#panelCard {{
        border-bottom: 2px solid {c.SURFACE2};
    }}
    QFrame#softCard {{
        background-color: {c.SURFACE1};
        border: 1px solid {c.BORDER};
        border-radius: 17px;
    }}
    QFrame#scheduleGrid {{
        background-color: transparent;
        border: 0;
        border-radius: 17px;
    }}
    QFrame#scheduleCourseCard {{
        background-color: transparent;
        border: 0;
    }}
    QLabel#scheduleHeader {{
        background-color: {c.SURFACE1};
        border: 1px solid {c.BORDER};
        border-radius: 10px;
        color: {c.SUBTEXT1};
        font-size: 12px;
        font-weight: 750;
    }}
    QLabel#scheduleSection {{
        background-color: {c.SURFACE1};
        border: 1px solid {c.BORDER};
        border-radius: 10px;
        color: {c.SUBTEXT0};
        font-size: 11px;
        font-weight: 700;
    }}
    QFrame#scheduleCell {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.BORDER};
        border-radius: 12px;
    }}
    QFrame#selectedCourseCard {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.BORDER};
        border-radius: 16px;
    }}
    QFrame#selectedCourseCard:hover {{
        background-color: {c.SURFACE1};
        border-color: {c.BLUE};
    }}
    QLabel#creditBadge, QLabel#courseCreditBadge {{
        color: {c.BLUE};
        background-color: {c.MANTLE};
        border: 1px solid {c.BORDER};
        border-radius: 9px;
        padding: 3px 8px;
        font-size: 11px;
        font-weight: 650;
    }}
    QLabel {{
        background-color: transparent;
        color: {c.TEXT};
    }}
    QLabel#brandTitle {{
        font-size: 30px;
        font-weight: 850;
        letter-spacing: 0.2px;
        color: {c.TEXT};
    }}
    QLabel#brandSubtitle, QLabel#mutedLabel {{
        color: {c.SUBTEXT0};
    }}
    QLabel#pageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {c.TEXT};
    }}
    QLabel#homeTitle {{
        font-size: 22px;
        font-weight: 850;
        letter-spacing: 0.2px;
        color: {c.TEXT};
    }}
    QLabel#sectionTitle {{
        font-size: 16px;
        font-weight: 700;
        color: {c.TEXT};
    }}
    QLabel#fieldLabel {{
        color: {c.SUBTEXT1};
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#statusPill, QLabel#batchPill {{
        background-color: {c.SURFACE1};
        border: 1px solid {c.BORDER};
        border-radius: 16px;
        color: {c.SUBTEXT1};
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 650;
    }}
    QLabel#runPill {{
        background-color: transparent;
        border: none;
        padding: 0;
        font-size: 12px;
        font-weight: 650;
    }}
    QLabel#loginFeedback {{
        color: {c.RED};
        font-size: 12px;
        min-height: 18px;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.SURFACE2};
        border-radius: 13px;
        padding: 9px 12px;
        color: {c.TEXT};
        selection-background-color: {c.BLUE};
    }}
    QFrame#loginInputFrame {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.SURFACE2};
        border-radius: 15px;
    }}
    QFrame#loginInputFrame:hover {{
        border-color: {c.OVERLAY0};
    }}
    QFrame#loginInputFrame[focused="true"] {{
        border: 2px solid {c.BLUE};
    }}
    QLineEdit#loginLineEdit,
    QLineEdit#loginLineEdit:hover,
    QLineEdit#loginLineEdit:focus,
    QLineEdit#loginLineEdit:disabled {{
        background-color: transparent;
        border: 0;
        border-radius: 0;
        padding: 0;
        color: {c.TEXT};
        font-size: 16px;
        font-weight: 550;
        selection-background-color: {c.BLUE};
    }}
    QLabel#loginFloatingLabel {{
        background-color: {c.SURFACE0};
        color: {c.BLUE};
        padding: 0 5px;
        font-size: 11px;
        font-weight: 650;
    }}
    QToolButton#loginEyeButton {{
        background-color: transparent;
        border: 0;
        border-radius: 10px;
        padding: 5px;
    }}
    QToolButton#loginEyeButton:hover {{ background-color: {c.SURFACE1}; }}
    QToolButton#loginEyeButton:pressed {{ background-color: {c.SURFACE2}; }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
        border-color: {c.OVERLAY0};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 2px solid {c.BLUE};
        padding: 8px 11px;
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background-color: {c.SURFACE1};
        color: {c.OVERLAY0};
    }}
    QFrame#inlineSpinBox {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.SURFACE2};
        border-radius: 13px;
    }}
    QFrame#inlineSpinBox:hover {{
        border-color: {c.OVERLAY0};
    }}
    QSpinBox#inlineSpinValue, QSpinBox#inlineSpinValue:hover,
    QSpinBox#inlineSpinValue:focus, QSpinBox#inlineSpinValue:disabled {{
        background-color: transparent;
        border: 0;
        border-radius: 0;
        padding: 0;
        color: {c.TEXT};
        font-weight: 750;
    }}
    QToolButton#spinStepButton {{
        background-color: transparent;
        border: 0;
        border-radius: 9px;
        color: {c.SUBTEXT0};
        padding: 0;
        font-size: 18px;
        font-weight: 600;
    }}
    QToolButton#spinStepButton:hover {{
        background-color: {c.SURFACE1};
        color: {c.BLUE};
    }}
    QToolButton#spinStepButton:pressed {{
        background-color: {c.SURFACE2};
    }}
    QToolButton#spinStepButton:disabled {{
        background-color: transparent;
        color: {c.SURFACE2};
    }}
    QComboBox::drop-down {{ border: 0; width: 34px; }}
    QComboBox QAbstractItemView {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.BORDER};
        border-radius: 14px;
        color: {c.TEXT};
        selection-background-color: {c.SURFACE1};
        outline: 0;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 38px;
        padding: 4px 12px;
        border-radius: 9px;
    }}
    QPushButton {{
        background-color: {c.BLUE};
        color: white;
        border: 0;
        border-radius: 13px;
        padding: 9px 16px;
        font-weight: 650;
    }}
    QPushButton:hover {{ background-color: {c.SAPPHIRE}; }}
    QPushButton:pressed {{ background-color: {c.LAVENDER}; }}
    QPushButton:disabled {{ background-color: {c.SURFACE2}; color: {c.OVERLAY0}; }}
    QPushButton#primaryButton {{
        font-size: 15px;
        font-weight: 700;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.BLUE}, stop:1 {c.SAPPHIRE});
    }}
    QPushButton#primaryButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.LAVENDER}, stop:1 {c.BLUE});
    }}
    QPushButton#secondaryButton {{
        background-color: {c.SURFACE0};
        color: {c.SUBTEXT1};
        border: 1px solid {c.SURFACE2};
    }}
    QPushButton#secondaryButton:hover {{ background-color: {c.SURFACE1}; border-color: {c.OVERLAY0}; }}
    QPushButton#successButton {{ background-color: {c.GREEN}; color: white; }}
    QPushButton#successButton:hover {{ background-color: #0E9F5F; }}
    QPushButton#dangerButton {{ background-color: {c.RED}; color: white; }}
    QPushButton#dangerButton:hover {{ background-color: #D92D20; }}
    QToolButton {{
        background-color: transparent;
        border: 0;
        border-radius: 11px;
        padding: 7px;
        color: {c.SUBTEXT0};
    }}
    QToolButton:hover {{ background-color: {c.SURFACE1}; color: {c.TEXT}; }}
    QToolButton:pressed {{ background-color: {c.MANTLE}; }}
    QToolButton#grabRemoveButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 5px;
    }}
    QToolButton#grabRemoveButton:hover {{
        background-color: {c.MANTLE};
        border-color: {c.SURFACE2};
    }}
    QListWidget {{
        background-color: {c.SURFACE0};
        border: 1px solid {c.BORDER};
        border-radius: 17px;
        padding: 6px;
        outline: 0;
    }}
    QListWidget::item {{
        border-radius: 12px;
        padding: 10px 12px;
        margin: 2px 0;
        color: {c.TEXT};
    }}
    QListWidget#grabList::item {{ padding-right: 46px; }}
    QListWidget::item:hover {{ background-color: {c.SURFACE1}; }}
    QListWidget::item:selected {{ background-color: {c.MANTLE}; color: {c.BLUE}; }}
    QTextEdit {{
        background-color: {c.SURFACE0};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        border-radius: 17px;
        padding: 10px;
        selection-background-color: {c.BLUE};
    }}
    QTextEdit#logConsole {{
        background-color: {c.TERMINAL};
        color: {c.TERMINAL_TEXT};
        border: 1px solid {c.SURFACE2};
        font-family: "HarmonyOS Sans SC", sans-serif;
        font-size: 12px;
    }}
    QProgressBar {{
        background-color: {c.SURFACE1};
        border: 0;
        border-radius: 3px;
        max-height: 6px;
        min-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background-color: {c.BLUE}; border-radius: 3px; }}
    QCheckBox {{ color: {c.SUBTEXT1}; spacing: 9px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border: 1px solid {c.SURFACE2};
        border-radius: 5px;
        background-color: {c.SURFACE0};
    }}
    QCheckBox::indicator:checked {{ background-color: {c.BLUE}; border-color: {c.BLUE}; }}
    QScrollArea {{ background-color: transparent; border: 0; }}
    QScrollArea > QWidget > QWidget {{ background-color: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 3px; }}
    QScrollBar::handle:vertical {{ background: {c.SURFACE2}; border-radius: 3px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {c.OVERLAY0}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QSplitter::handle {{ background-color: transparent; width: 10px; }}
    QMenuBar {{ background-color: {c.SURFACE0}; color: {c.TEXT}; border-bottom: 1px solid {c.BORDER}; }}
    QMenuBar::item {{ padding: 7px 12px; border-radius: 7px; }}
    QMenuBar::item:selected {{ background-color: {c.SURFACE1}; }}
    QMenu {{
        background-color: {c.SURFACE0};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        border-radius: 14px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 10px 32px 10px 20px; border-radius: 10px; }}
    QMenu::icon {{ margin-left: 6px; }}
    QMenu::item:selected {{ background-color: {c.SURFACE1}; }}
    QStatusBar {{ background-color: {c.SURFACE0}; color: {c.SUBTEXT0}; border-top: 1px solid {c.BORDER}; }}
    QStatusBar::item {{
        background-color: transparent;
        border: none;
    }}
    QToolTip {{
        background-color: {c.SURFACE0};
        color: {c.TEXT};
        border: 1px solid {c.SURFACE2};
        border-radius: 10px;
        padding: 7px 10px;
        font-size: 12px;
        font-weight: 600;
    }}
    QDialogButtonBox QPushButton {{ min-width: 86px; min-height: 22px; }}
    QMessageBox QLabel {{ color: {c.TEXT}; min-width: 280px; padding: 4px; }}
    """


def build_tooltip_stylesheet(mode="light"):
    """Style top-level tooltip windows without reapplying the full app QSS."""
    apply_palette(mode)
    c = Colors
    return f"""
    QToolTip {{
        background-color: {c.SURFACE0};
        color: {c.TEXT};
        border: 1px solid {c.SURFACE2};
        border-radius: 10px;
        padding: 7px 10px;
        font-family: "HarmonyOS Sans SC", sans-serif;
        font-size: 12px;
        font-weight: 600;
    }}
    """
