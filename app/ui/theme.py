"""Design tokens and the application stylesheet (dark charcoal, muted orange accent)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# --- color tokens ----------------------------------------------------------
BG = "#1B1C1F"          # window background
PANEL = "#232427"       # docks, panels
SURFACE = "#2B2D31"     # inputs, cards
SURFACE_HI = "#33363B"  # hover
BORDER = "#3A3D43"
TEXT = "#E6E6E3"        # contrast on BG ~ 13:1
TEXT_MUTED = "#A9ABB0"  # ~ 7:1 on PANEL
ACCENT = "#D08C4B"      # muted orange; dark text on it ~ 6:1
ACCENT_HI = "#E0A266"
ACCENT_DIM = "#8A5C33"
ERROR = "#E5736A"
WARNING = "#E2B24E"
OK = "#7FBF7F"
PAPER = "#ECE9E2"       # page canvas behind preview pages

# --- spacing / sizing tokens -------------------------------------------------
SP_1, SP_2, SP_3, SP_4 = 4, 8, 12, 16
RADIUS = 5
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10


def stylesheet(check_icon: str = "") -> str:
    check_rule = f"image: url({check_icon});" if check_icon else ""
    return f"""
* {{ font-family: '{FONT_FAMILY}', 'Segoe UI Variable', Arial, sans-serif; font-size: {FONT_SIZE}pt; }}
QMainWindow, QDialog, QWizard {{ background: {BG}; color: {TEXT}; }}
QWidget {{ color: {TEXT}; }}
QDockWidget {{ titlebar-close-icon: none; color: {TEXT_MUTED}; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 10px; border-bottom: 1px solid {BORDER};
    text-transform: uppercase; }}
QToolBar {{ background: {PANEL}; border: 0; border-bottom: 1px solid {BORDER}; spacing: 4px;
    padding: 4px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {RADIUS}px;
    padding: 5px 9px; color: {TEXT}; }}
QToolButton:hover {{ background: {SURFACE_HI}; border-color: {BORDER}; }}
QToolButton:pressed, QToolButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QToolButton:disabled {{ color: #6B6D72; }}
QToolButton:focus, QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QTreeView:focus, QListWidget:focus {{ border: 1px solid {ACCENT}; }}
QMenuBar {{ background: {PANEL}; color: {TEXT}; }}
QMenuBar::item:selected {{ background: {SURFACE_HI}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 3px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: #6B6D72; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ padding: 0 8px; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
QTreeWidget, QTableWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    selection-background-color: {ACCENT_DIM}; selection-color: {TEXT}; padding: 3px 5px; }}
QTreeWidget, QListWidget {{ padding: 2px; outline: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 4px 4px; border-radius: 3px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {SURFACE_HI}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QComboBox::drop-down {{ border: 0; width: 20px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; selection-background-color: {ACCENT_DIM}; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    padding: 6px 14px; }}
QPushButton:hover {{ background: {SURFACE_HI}; }}
QPushButton:default, QPushButton[accent="true"] {{ background: {ACCENT}; color: #1B1C1F;
    border-color: {ACCENT_HI}; font-weight: 600; }}
QPushButton:default:hover, QPushButton[accent="true"]:hover {{ background: {ACCENT_HI}; }}
QPushButton:disabled {{ color: #6B6D72; background: {PANEL}; }}
QCheckBox, QRadioButton, QLabel {{ background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{ border: 1px solid {BORDER}; border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HI}; {check_rule} }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: {RADIUS}px; margin-top: 14px; padding-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {TEXT_MUTED}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: {RADIUS}px; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 6px 12px;
    border-top-left-radius: {RADIUS}px; border-top-right-radius: {RADIUS}px; color: {TEXT_MUTED}; }}
QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; border-bottom-color: {SURFACE}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 12px; margin: 0; }}
QScrollBar:horizontal {{ background: {PANEL}; height: 12px; margin: 0; }}
QScrollBar::handle {{ background: #4A4D54; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}
QProgressBar {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px; text-align: center;
    height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {ACCENT_DIM}; padding: 4px; }}
QHeaderView::section {{ background: {PANEL}; color: {TEXT_MUTED}; border: 0; padding: 4px 8px; }}
QLabel[muted="true"] {{ color: {TEXT_MUTED}; }}
QLabel[heading="true"] {{ font-size: 12pt; font-weight: 600; }}
"""


def _write_check_icon() -> str:
    """Write the checkbox tick as an SVG (Qt style sheets need a file) and return its URL path."""
    try:
        from ..services.app_paths import user_data_dir
        d = user_data_dir() / "icons"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "check.svg"
        f.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
                     '<path d="M3 7.5l3 3 5-6" stroke="#1B1C1F" stroke-width="2" fill="none" '
                     'stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
        return f.as_posix()
    except OSError:
        return ""


def apply_theme(app: QApplication, scale: float = 1.0) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(SURFACE))
    pal.setColor(QPalette.AlternateBase, QColor(PANEL))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT_DIM))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(SURFACE))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT_MUTED))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#6B6D72"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6B6D72"))
    pal.setColor(QPalette.Link, QColor(ACCENT_HI))
    app.setPalette(pal)
    f = QFont(FONT_FAMILY, int(round(FONT_SIZE * scale)))
    app.setFont(f)
    app.setStyleSheet(stylesheet(_write_check_icon()))


def set_muted(widget) -> None:
    widget.setProperty("muted", True)


def set_heading(widget) -> None:
    widget.setProperty("heading", True)


def accent_button(button) -> None:
    button.setProperty("accent", True)
